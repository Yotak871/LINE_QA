import uuid
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles

from app.models.database import Analysis, Difference, get_db
from app.core.config import UPLOAD_PATH
from app.services.image_processor import load_and_normalize, save_marked_image, get_image_dimensions, scale_regions_to_original
from app.services.pixel_diff import compute_diff
from app.services.gemini_analyzer import analyze_with_gemini

router = APIRouter(prefix="/api/analyze", tags=["analyze"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


async def _save_upload(file: UploadFile, dest: Path) -> str:
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "파일이 너무 큽니다. 20MB 이하로 올려주세요.")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "지원하지 않는 형식입니다. PNG, JPG, WebP만 가능합니다.")
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
    return str(dest)


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
            await db.commit()

            design_path = analysis.design_image_path
            dev_path = analysis.dev_image_path

            # Step 1: 원본 이미지 크기 조회
            dev_w, dev_h = get_image_dimensions(dev_path)
            print(f"[Analysis] 개발 이미지 크기: {dev_w}x{dev_h}")

            # Step 2: 이미지 정규화 + 픽셀 비교
            img_a, img_b, orig_a_size, orig_b_size = load_and_normalize(design_path, dev_path)
            norm_h, norm_w = img_b.shape[:2]
            print(f"[Analysis] 정규화 크기: {norm_w}x{norm_h}")

            similarity, regions = compute_diff(img_a, img_b)
            analysis.similarity_score = similarity
            print(f"[Analysis] 유사도: {similarity}%, 픽셀 diff 영역: {len(regions)}개")

            # Step 3: 픽셀 diff 영역을 원본 이미지 좌표로 스케일링
            scaled_regions = scale_regions_to_original(regions, norm_w, norm_h, dev_w, dev_h)

            # Step 4: Gemini Vision AI 분석 (원본 이미지 경로 전달)
            diff_data = await analyze_with_gemini(
                design_path=design_path,
                dev_path=dev_path,
                regions=scaled_regions,
                dev_width=dev_w,
                dev_height=dev_h,
            )
            print(f"[Analysis] Gemini 분석 결과: {len(diff_data)}개 차이점")

            # Step 5: 마킹 이미지 생성
            marked_path = str(UPLOAD_PATH / f"{analysis_id}_marked.png")
            save_marked_image(dev_path, diff_data, marked_path)
            analysis.marked_image_path = marked_path

            # Step 6: DB 저장
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


@router.post("")
async def start_analysis(
    background_tasks: BackgroundTasks,
    design_image: UploadFile = File(...),
    dev_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """이미지 2장을 업로드하고 분석을 시작한다."""
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
    )
    db.add(analysis)
    await db.commit()

    background_tasks.add_task(_run_analysis, analysis_id)

    return {"analysis_id": analysis_id, "status": "pending"}


@router.get("/{analysis_id}/status")
async def get_status(analysis_id: str, db: AsyncSession = Depends(get_db)):
    """분석 진행 상태를 반환한다."""
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "분석을 찾을 수 없습니다.")
    return {
        "status": analysis.status,
        "similarity_score": analysis.similarity_score,
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
