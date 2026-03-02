import uuid
import asyncio
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles

from app.models.database import Analysis, Difference, get_db
from app.core.config import UPLOAD_PATH, settings
from app.services.image_processor import load_and_normalize, save_marked_image, get_image_dimensions, scale_regions_to_original
from app.services.pixel_diff import compute_diff
from app.services.element_analyzer import detect_and_compare, format_differences_with_labels, analyze_pixel_regions
from app.services.gemini_analyzer import label_bands, find_visual_diffs, analyze_uncovered_regions
router = APIRouter(prefix="/api/analyze", tags=["analyze"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# ─── Rate Limiting (IP당 분석 횟수 제한) ───
# 배포 시 Gemini API 비용 보호용
RATE_LIMIT_WINDOW = 3600  # 1시간
RATE_LIMIT_MAX = 20       # 시간당 최대 20회 분석
_rate_store: dict = defaultdict(list)


def _check_rate_limit(client_ip: str):
    """IP 기반 rate limiting. 초과 시 429 에러."""
    now = time.time()
    # 윈도우 밖의 기록 정리
    _rate_store[client_ip] = [
        t for t in _rate_store[client_ip] if now - t < RATE_LIMIT_WINDOW
    ]
    if len(_rate_store[client_ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            429,
            f"분석 요청이 너무 많습니다. {RATE_LIMIT_WINDOW // 60}분 후에 다시 시도해주세요."
        )
    _rate_store[client_ip].append(now)


async def _save_upload(file: UploadFile, dest: Path) -> str:
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "파일이 너무 큽니다. 20MB 이하로 올려주세요.")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "지원하지 않는 형식입니다. PNG, JPG, WebP만 가능합니다.")
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
    return str(dest)


def _pixel_regions_to_diffs(
    regions: list, dev_w: int, dev_h: int,
) -> list:
    """
    픽셀 차이 영역을 표시 가능한 diff 형식으로 변환.

    AI가 실패해도 사용자에게 차이 영역을 보여주는 안전장치.
    compute_diff()의 pixel_regions는 100% 정확하므로 (SSIM + 3-pass),
    이 데이터 자체가 이미 유효한 QA 결과.
    """
    diffs = []
    total_area = dev_w * dev_h

    for r in regions:
        area = r["w"] * r["h"]
        area_ratio = area / total_area if total_area > 0 else 0

        # 면적 기반 심각도
        if area_ratio > 0.03:
            severity = "critical"
        elif area_ratio > 0.01:
            severity = "major"
        else:
            severity = "minor"

        # 위치 기반 설명
        rel_y = (r["y"] + r["h"] / 2) / dev_h
        sensitivity = r.get("sensitivity", "structural")
        if rel_y < 0.1:
            location = "상태바/헤더"
        elif rel_y < 0.25:
            location = "상단 콘텐츠"
        elif rel_y < 0.75:
            location = "본문 콘텐츠"
        elif rel_y < 0.9:
            location = "하단 콘텐츠"
        else:
            location = "하단 내비게이션"

        if sensitivity == "structural":
            desc = f"{location} 영역 구조적 차이 — 레이아웃 또는 요소 변경 감지"
        elif sensitivity == "detail":
            desc = f"{location} 영역 세부 차이 — 간격, 색상, 또는 타이포 변경 감지"
        elif sensitivity == "edge":
            desc = f"{location} 영역 경계 차이 — 마진/패딩 또는 보더 변경 감지"
        else:
            desc = f"{location} 영역 시각적 차이 감지"

        diffs.append({
            "category": "layout",
            "severity": severity,
            "description": desc,
            "design_value": "",
            "dev_value": "",
            "bbox_x": r["x"],
            "bbox_y": r["y"],
            "bbox_w": r["w"],
            "bbox_h": r["h"],
        })

    return diffs


def _deduplicate_qa_results(diffs: list, img_h: int, img_w: int = 0) -> list:
    """
    v12.1: 인과관계 기반 QA 결과 정리.

    핵심 원칙: "근본 원인만 보고하고, 연쇄 효과는 제거한다."

    예시:
      #2 spacing: 콘텐츠↔텍스트 간격 65px→42px (-23px)  ← 근본 원인
      #4 visual: 본문 영역 시각적 차이                     ← #2의 연쇄 효과 → 제거
      #5 visual: 본문 영역 시각적 차이                     ← #2의 연쇄 효과 → 제거

    v12.1: is_wide 버그 수정 — 실제 화면 너비의 40% 이상만 넓은 영역으로 판정

    5단계 파이프라인:
      1. 카테고리 분류 (spacing = 근본 원인 후보)
      2. 연쇄 효과 제거 — spacing 아래의 position shift/visual diff
      3. 동일 영역 중복 제거 (bbox 겹침)
      4. spacing 간 인과관계 정리 (누적 효과)
      5. 심각도 + 카테고리 순 정렬
    """
    if not diffs:
        return diffs

    # ── 1단계: 카테고리별 분류 ──
    spacing_diffs = []
    other_diffs = []
    for d in diffs:
        if d.get("category", "") == "spacing":
            spacing_diffs.append(d)
        else:
            other_diffs.append(d)

    # spacing diff에서 근본 원인 정보 추출
    # {y위치, 변화량, 영향 시작점(y_end)}
    spacing_causes = []
    for sd in spacing_diffs:
        try:
            d_val = int(sd.get("design_value", "0").replace("px", ""))
            v_val = int(sd.get("dev_value", "0").replace("px", ""))
            delta = abs(d_val - v_val)
            bbox_y = sd.get("bbox_y", 0)
            bbox_h = sd.get("bbox_h", 0)
            # 이 spacing diff의 영향 범위: bbox 아래쪽 전부
            affect_start_y = bbox_y + bbox_h
            spacing_causes.append({
                "delta": delta,
                "y": bbox_y,
                "affect_start_y": affect_start_y,
            })
        except (ValueError, TypeError):
            pass

    # ── 2단계: 연쇄 효과 제거 (인과관계 기반) ──
    filtered_others = []
    cascade_removed = 0

    for d in other_diffs:
        cat = d.get("category", "")
        desc = d.get("description", "")
        diff_y = d.get("bbox_y", 0)
        diff_h = d.get("bbox_h", 0)
        diff_w = d.get("bbox_w", 0)

        should_remove = False

        # 2a: "이동" 키워드 기반 position shift 제거 (기존 v9 로직)
        if "이동" in desc and spacing_causes:
            above = [sc for sc in spacing_causes if sc["affect_start_y"] <= diff_y + diff_h]
            if above:
                should_remove = True

        # 2b: 인과관계 기반 연쇄 효과 제거 (v12 신규)
        # spacing diff 아래에 있는 visual/layout diff 중,
        # "넓은 영역"의 시각적 차이는 위치 이동의 결과일 가능성 높음
        if not should_remove and spacing_causes and cat in ("visual", "layout"):
            for sc in spacing_causes:
                # 조건 1: 이 diff가 spacing diff의 영향 범위 아래에 있는가?
                if diff_y < sc["affect_start_y"]:
                    continue

                # 조건 2: 넓은 영역인가? (화면 폭의 40% 이상)
                # 좁은 영역(특정 버튼 색상 다름 등)은 독립적 이슈일 수 있음
                # v12.1: 버그 수정 — 실제 너비 비율 체크 (기존: 항상 True)
                is_wide = img_w > 0 and diff_w > img_w * 0.4
                if not is_wide:
                    continue

                # 조건 3: visual diff인데 구체적 수치가 없는 경우
                # (AI가 "시각적 차이 감지"라고만 한 것 = 위치 이동 결과)
                has_specific_value = (
                    d.get("design_value") and d.get("dev_value")
                    and "px" in str(d.get("design_value", ""))
                )
                if cat == "visual" and not has_specific_value:
                    should_remove = True
                    break

                # 조건 4: layout diff인데 변화량이 spacing delta와 유사
                # (spacing 변화로 인한 높이/위치 변화)
                if cat == "layout" and has_specific_value:
                    try:
                        d_val = int(str(d.get("design_value", "0")).replace("px", ""))
                        v_val = int(str(d.get("dev_value", "0")).replace("px", ""))
                        this_delta = abs(d_val - v_val)
                        # 누적 spacing delta와 비교
                        cumulative = sum(
                            s["delta"] for s in spacing_causes
                            if s["affect_start_y"] <= diff_y + diff_h
                        )
                        if cumulative > 0 and abs(this_delta - cumulative) <= 10:
                            should_remove = True
                            break
                    except (ValueError, TypeError):
                        pass

        if should_remove:
            cascade_removed += 1
            print(f"  [연쇄제거] {cat}: {desc[:40]}... (Y={diff_y})")
        else:
            filtered_others.append(d)

    # ── 3단계: 동일 영역 중복 제거 (bbox 겹침 기반) ──
    combined = spacing_diffs + filtered_others
    final = []
    for d in combined:
        is_dup = False
        dy = d.get("bbox_y", 0)
        dh = d.get("bbox_h", 0)

        for j, existing in enumerate(final):
            ey = existing.get("bbox_y", 0)
            eh = existing.get("bbox_h", 0)

            overlap_start = max(dy, ey)
            overlap_end = min(dy + dh, ey + eh)
            if overlap_end > overlap_start:
                overlap = overlap_end - overlap_start
                min_h = min(dh, eh)
                if min_h > 0 and overlap / min_h > 0.8:
                    # 더 구체적인(spacing > layout > visual) 것을 유지
                    priority = {"spacing": 0, "content": 1, "layout": 2,
                                "typography": 3, "visual": 4}
                    d_pri = priority.get(d.get("category", ""), 5)
                    e_pri = priority.get(existing.get("category", ""), 5)
                    if d_pri < e_pri:
                        final[j] = d
                    is_dup = True
                    break

        if not is_dup:
            final.append(d)

    # ── 4단계: spacing 간 인과관계 정리 ──
    # 같은 위치의 spacing이 여러 개면 가장 구체적인 것만 유지
    # (예: "콘텐츠↔텍스트 간격" + "섹션 간격"이 같은 Y면 하나만)
    seen_y_ranges = []
    deduped_final = []
    for d in final:
        dy = d.get("bbox_y", 0)
        dh = d.get("bbox_h", 0)

        # 이미 같은 Y 범위에 spacing이 있으면 skip
        is_y_dup = False
        for sy, sh in seen_y_ranges:
            if abs(dy - sy) < 15 and d.get("category") == "spacing":
                is_y_dup = True
                break
        if is_y_dup:
            continue

        if d.get("category") == "spacing":
            seen_y_ranges.append((dy, dh))
        deduped_final.append(d)

    # ── 5단계: 심각도 + 카테고리 순 정렬 ──
    cat_order = {"spacing": 0, "content": 1, "layout": 2,
                 "typography": 3, "visual": 4}
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    deduped_final.sort(key=lambda d: (
        sev_order.get(d.get("severity", "minor"), 3),
        cat_order.get(d.get("category", "visual"), 5),
        d.get("bbox_y", 0),
    ))

    print(f"  [QA정리v12] 연쇄효과 {cascade_removed}개 제거, "
          f"최종 {len(deduped_final)}개 (원본 {len(diffs)}개)")
    return deduped_final


def _find_uncovered_regions(
    pixel_regions: list, cv_diffs: list, coverage_thresh: float = 0.5
) -> list:
    """pixel diff 영역 중 CV가 커버하지 못한 영역만 추출."""
    uncovered = []
    for pr in pixel_regions:
        px, py, pw, ph = pr["x"], pr["y"], pr["w"], pr["h"]
        pr_area = pw * ph
        if pr_area <= 0:
            continue

        # CV diff bbox들과 겹침 비율 계산
        max_coverage = 0.0
        for cd in cv_diffs:
            cx = cd.get("bbox_x", 0)
            cy = cd.get("bbox_y", 0)
            cw = cd.get("bbox_w", 0)
            ch = cd.get("bbox_h", 0)

            ix1 = max(px, cx)
            iy1 = max(py, cy)
            ix2 = min(px + pw, cx + cw)
            iy2 = min(py + ph, cy + ch)

            if ix2 > ix1 and iy2 > iy1:
                inter = (ix2 - ix1) * (iy2 - iy1)
                coverage = inter / pr_area
                max_coverage = max(max_coverage, coverage)

        if max_coverage < coverage_thresh:
            uncovered.append(pr)

    return uncovered


async def _run_analysis(analysis_id: str):
    """BackgroundTask: 실제 AI 분석 파이프라인 실행."""
    from app.models.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
        analysis = result.scalar_one_or_none()
        if not analysis:
            return

        try:
            analysis.status = "processing"
            analysis.progress_step = "normalize"
            await db.commit()

            design_path = analysis.design_image_path
            dev_path = analysis.dev_image_path

            # Step 1: 원본 이미지 크기 조회
            dev_w, dev_h = get_image_dimensions(dev_path)
            print(f"[Analysis] 개발 이미지 크기: {dev_w}x{dev_h}")

            # Step 2: 픽셀 비교 (유사도 + 차이 영역 — ground truth)
            img_a, img_b, orig_a_size, orig_b_size = load_and_normalize(design_path, dev_path)
            norm_h, norm_w = img_b.shape[:2]
            similarity, pixel_regions = compute_diff(img_a, img_b)
            analysis.similarity_score = similarity
            print(f"[Analysis] 유사도: {similarity}%, pixel diff 영역: {len(pixel_regions)}개")

            # pixel_regions 좌표를 정규화 공간 → 원본 dev 공간으로 변환
            scale_x = dev_w / norm_w if norm_w > 0 else 1.0
            scale_y = dev_h / norm_h if norm_h > 0 else 1.0
            for r in pixel_regions:
                r["x"] = int(r["x"] * scale_x)
                r["y"] = int(r["y"] * scale_y)
                r["w"] = int(r["w"] * scale_x)
                r["h"] = int(r["h"] * scale_y)

            # ═══ CV 측정 + AI 라벨링 파이프라인 ═══

            # Step 3: CV 기반 정밀 측정 — 간격, 마진, 높이
            analysis.progress_step = "cv_measure"
            await db.commit()
            cv_diffs, design_bands, dev_bands = detect_and_compare(design_path, dev_path)
            print(f"[Analysis] CV 측정: {len(cv_diffs)}개 간격 차이, "
                  f"밴드 {len(design_bands)}(디자인)/{len(dev_bands)}(개발)")

            # Step 4: Gemini AI — 밴드 라벨링 + 시각적 차이 감지
            # 4a: 밴드에 의미론적 이름 부여
            analysis.progress_step = "ai_label"
            await db.commit()
            labels = await label_bands(dev_path, dev_bands)
            print(f"[Analysis] AI 라벨: {labels}")

            # 4b: CV 측정 결과를 라벨과 결합하여 사람이 읽을 수 있는 형태로 변환
            spacing_diffs = format_differences_with_labels(
                cv_diffs, design_bands, dev_bands, labels, dev_w, dev_h,
            )

            # 4b-2: design_bbox 좌표를 정규화 공간 → 원본 디자인 공간으로 변환
            design_w_orig, design_h_orig = get_image_dimensions(design_path)
            scale_back = design_w_orig / dev_w if dev_w > 0 else 1.0
            for d in spacing_diffs:
                if "design_bbox_x" in d:
                    d["design_bbox_x"] = int(d["design_bbox_x"] * scale_back)
                    d["design_bbox_y"] = int(d["design_bbox_y"] * scale_back)
                    d["design_bbox_w"] = int(d["design_bbox_w"] * scale_back)
                    d["design_bbox_h"] = int(d["design_bbox_h"] * scale_back)

            # 4c: pixel diff 영역 중 CV가 커버하지 못한 영역 추출
            analysis.progress_step = "ai_visual"
            await db.commit()

            uncovered = _find_uncovered_regions(pixel_regions, spacing_diffs)
            print(f"[Analysis] pixel diff {len(pixel_regions)}개 중 미커버: {len(uncovered)}개")

            # 4d: 미커버 영역을 Gemini에 타겟 분석 + 전체 비-간격 차이 감지
            visual_diffs = await find_visual_diffs(design_path, dev_path, dev_w, dev_h)
            targeted_diffs = await analyze_uncovered_regions(
                design_path, dev_path, uncovered, dev_w, dev_h
            )

            # Step 5: 결과 통합 — CV(정확) + AI 전체(보완) + AI 타겟(미커버)
            analysis.progress_step = "finalize"
            await db.commit()
            diff_data = spacing_diffs + visual_diffs + targeted_diffs
            print(f"[Analysis] 최종: CV {len(spacing_diffs)}개 + AI전체 {len(visual_diffs)}개 + AI타겟 {len(targeted_diffs)}개 = {len(diff_data)}개")

            # ── v7: 픽셀 diff 영역 CV 정밀 분석 (AI 대체) ──
            final_uncovered = _find_uncovered_regions(pixel_regions, diff_data)
            if final_uncovered:
                pixel_cv_diffs = analyze_pixel_regions(
                    design_path, dev_path, final_uncovered, dev_w, dev_h
                )
                if pixel_cv_diffs:
                    for d in pixel_cv_diffs:
                        if "design_bbox_x" in d:
                            d["design_bbox_x"] = int(d["design_bbox_x"] * scale_back)
                            d["design_bbox_y"] = int(d["design_bbox_y"] * scale_back)
                            d["design_bbox_w"] = int(d["design_bbox_w"] * scale_back)
                            d["design_bbox_h"] = int(d["design_bbox_h"] * scale_back)
                    diff_data.extend(pixel_cv_diffs)
                    print(f"[Analysis] 픽셀CV 분석: 미커버 {len(final_uncovered)}개 → {len(pixel_cv_diffs)}개 추가")

            # ── v9: QA 결과 정리 (UX디자이너→개발자 전달 관점) ──
            before_count = len(diff_data)
            diff_data = _deduplicate_qa_results(diff_data, dev_h, dev_w)
            print(f"[Analysis] QA정리: {before_count}개 → {len(diff_data)}개 (중복/무의미 {before_count - len(diff_data)}개 제거)")

            # Step 6: 마킹 이미지 생성
            marked_path = str(UPLOAD_PATH / f"{analysis_id}_marked.png")
            save_marked_image(dev_path, diff_data, marked_path)
            analysis.marked_image_path = marked_path

            # Step 7: DB 저장
            for d in diff_data:
                diff = Difference(
                    analysis_id=analysis_id,
                    category=d["category"],
                    severity=d["severity"],
                    description=d["description"],
                    design_value=d.get("design_value", ""),
                    dev_value=d.get("dev_value", ""),
                    bbox_x=d.get("bbox_x", 0),
                    bbox_y=d.get("bbox_y", 0),
                    bbox_w=d.get("bbox_w", 0),
                    bbox_h=d.get("bbox_h", 0),
                    design_bbox_x=d["design_bbox_x"] if "design_bbox_x" in d else 0,
                    design_bbox_y=d["design_bbox_y"] if "design_bbox_y" in d else 0,
                    design_bbox_w=d["design_bbox_w"] if "design_bbox_w" in d else 0,
                    design_bbox_h=d["design_bbox_h"] if "design_bbox_h" in d else 0,
                )
                db.add(diff)

            analysis.status = "done"
            await db.commit()
            print(f"[Analysis] 분석 완료: {analysis_id}")

        except Exception as e:
            print(f"[Analysis] 분석 실패: {e}")
            analysis.status = "failed"
            analysis.error_message = str(e)
            await db.commit()
            raise


def _select_pipeline(pipeline: str) -> str:
    """파이프라인 선택. 현재는 v1_cv만 지원."""
    return "v1_cv"


@router.post("")
async def start_analysis(
    request: Request,
    background_tasks: BackgroundTasks,
    design_image: UploadFile = File(...),
    dev_image: UploadFile = File(...),
    figma_url: str = Form(default=""),
    pipeline: str = Form(default="auto"),
    db: AsyncSession = Depends(get_db),
):
    """이미지 업로드 후 분석 시작."""
    # Rate limit 체크
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    selected_pipeline = _select_pipeline(pipeline)

    analysis_id = str(uuid.uuid4())
    design_path = UPLOAD_PATH / f"{analysis_id}_design{Path(design_image.filename).suffix}"
    dev_path = UPLOAD_PATH / f"{analysis_id}_dev{Path(dev_image.filename).suffix}"

    await _save_upload(design_image, design_path)
    await _save_upload(dev_image, dev_path)

    analysis = Analysis(
        id=analysis_id,
        design_image_path=str(design_path),
        dev_image_path=str(dev_path),
        status="pending",
        pipeline_version=selected_pipeline,
    )
    db.add(analysis)
    await db.commit()

    background_tasks.add_task(_run_analysis, analysis_id)
    print(f"[Pipeline] v1_cv 분석 시작: {analysis_id}")

    return {
        "analysis_id": analysis_id,
        "status": "pending",
        "pipeline_version": selected_pipeline,
    }


@router.get("/{analysis_id}/status")
async def get_status(analysis_id: str, db: AsyncSession = Depends(get_db)):
    """분석 진행 상태를 반환한다."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "분석을 찾을 수 없습니다.")
    return {
        "status": analysis.status,
        "progress_step": analysis.progress_step,
        "similarity_score": analysis.similarity_score,
        "pipeline_version": analysis.pipeline_version,
        "error_message": analysis.error_message,
    }


@router.get("/{analysis_id}/result")
async def get_result(analysis_id: str, db: AsyncSession = Depends(get_db)):
    """분석 결과 전체를 반환한다."""
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "분석을 찾을 수 없습니다.")
    if analysis.status != "done":
        raise HTTPException(400, f"분석이 완료되지 않았습니다. 현재 상태: {analysis.status}")

    diffs = await db.execute(
        select(Difference).where(Difference.analysis_id == analysis_id)
    )
    differences = diffs.scalars().all()

    summary = {"critical": 0, "major": 0, "minor": 0, "approved": 0, "ignored": 0}
    for d in differences:
        if d.status == "approved":
            summary["approved"] += 1
        elif d.status == "ignored":
            summary["ignored"] += 1
        else:
            summary[d.severity] = summary.get(d.severity, 0) + 1

    # 이미지 크기 정보 (프론트엔드 SVG viewBox 매핑용)
    design_w, design_h = get_image_dimensions(analysis.design_image_path)
    dev_w, dev_h = get_image_dimensions(analysis.dev_image_path)

    return {
        "analysis_id": analysis_id,
        "status": analysis.status,
        "similarity_score": analysis.similarity_score,
        "pipeline_version": analysis.pipeline_version,
        "input_mode": analysis.input_mode,
        "design_image": f"/api/files/{Path(analysis.design_image_path).name}",
        "dev_image": f"/api/files/{Path(analysis.dev_image_path).name}",
        "marked_image": f"/api/files/{Path(analysis.marked_image_path).name}" if analysis.marked_image_path else None,
        "design_image_size": {"width": design_w, "height": design_h},
        "dev_image_size": {"width": dev_w, "height": dev_h},
        "summary": summary,
        "differences": [
            {
                "id": d.id,
                "category": d.category,
                "severity": d.severity,
                "description": d.description,
                "design_value": d.design_value,
                "dev_value": d.dev_value,
                "bbox_x": d.bbox_x,
                "bbox_y": d.bbox_y,
                "bbox_w": d.bbox_w,
                "bbox_h": d.bbox_h,
                "design_bbox_x": d.design_bbox_x,
                "design_bbox_y": d.design_bbox_y,
                "design_bbox_w": d.design_bbox_w,
                "design_bbox_h": d.design_bbox_h,
                "status": d.status,
            }
            for d in differences
        ],
    }


@router.patch("/{analysis_id}/differences/{diff_id}")
async def update_difference_status(
    analysis_id: str,
    diff_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """차이점 항목의 상태를 변경한다 (issue / approved / ignored)."""
    new_status = body.get("status")
    if new_status not in ("issue", "approved", "ignored"):
        raise HTTPException(400, "status는 issue, approved, ignored 중 하나여야 합니다.")

    result = await db.execute(
        select(Difference).where(Difference.id == diff_id, Difference.analysis_id == analysis_id)
    )
    diff = result.scalar_one_or_none()
    if not diff:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")

    diff.status = new_status
    await db.commit()
    return {"id": diff_id, "status": new_status}
