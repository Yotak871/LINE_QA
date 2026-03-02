"""
CV 기반 UI 요소 감지 및 간격 정밀 측정 엔진 v10.

v8/v9 → v10 개선사항:
  10. 구조적 앵커(Structural Anchor) 기반 비교 아키텍처
      — 콘텐츠(텍스트) 변화에 강건한 구조 비교
      — 배경색 전환점 + 수평 분리선을 앵커로 감지
      — 앵커로 화면을 zone으로 분할 → zone 단위 매칭
      — 사전 검증: 구조적 유사도 게이트 (너무 다른 이미지 → 요소매칭 skip)

  이전 문제: 텍스트 내용(영어 vs 태국어)이 다르면 connected component가
  다른 blob을 만들어 → 요소 매칭이 엉뚱한 곳을 짝지음 → 잘못된 QA 결과

  해결: "콘텐츠가 아니라 구조를 비교한다"
  - 배경색 전환 = UI 섹션 경계 (콘텐츠 무관)
  - 수평 분리선 = 명시적 UI 구분 (콘텐츠 무관)
  - 이 앵커들로 화면을 zone으로 나눈 후, zone 간 매칭 → zone 내부 비교

v4 → v5 개선사항:
  9. 갭 중심(Gap-Centric) 간격 감지 아키텍처

v3 → v4 개선사항:
  7. 밴드 경계 정밀 보정 (content-edge refinement)
  8. 갭 전용 bbox (gap-only bbox) → v5에서 갭 중심으로 대체

v2 → v3 개선사항:
  6. 대형 밴드 하위 분해 (hierarchical sub-band detection)

v1 → v2 개선사항:
  1. 상태바 영역 자동 제외
  2. 밴드 감지 강화 (적응형 임계값 + 노이즈 필터링)
  3. 시각적 유사도 기반 밴드 매칭 (히스토그램 상관 + 순서 보존)
  4. 비례적 심각도 (절대 px + 상대 비율 결합)
  5. 겹치는 차이 자동 병합
"""
from __future__ import annotations

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from skimage.metrics import structural_similarity as ssim

# ═══════════════════════════════════════════════════════════
# 설정 상수
# ═══════════════════════════════════════════════════════════
STATUS_BAR_RATIO = 0.07        # 상단 7% = 상태바 제외 영역 (iPhone Dynamic Island 포함)
CONTENT_THRESH = 0.025         # 행의 2.5% 이상이 콘텐츠면 밴드 내부 (fallback)
CONTENT_THRESH_ADAPTIVE = True # v11: 적응형 임계값 활성화
MIN_SPACING_DIFF = 2           # 간격 차이 최소 임계값 px (v11: 4→2, 미세 간격 감지)
MIN_HEIGHT_DIFF = 4            # 높이 차이 최소 임계값 px (v11: 5→4)
MIN_MARGIN_DIFF = 2            # 마진 차이 최소 임계값 px (v11: 4→2, 미세 마진 감지)
MATCH_MIN_SCORE = 0.25         # 밴드 매칭 최소 유사도 점수
MATCH_HIGH_CONFIDENCE = 0.55   # CV diff 생성 최소 매칭 신뢰도 (이하 → AI에 위임)
MIN_BAND_SIZE_RATIO = 0.35     # 매칭 밴드 높이 비율 최소값 (이하 → 다른 요소로 판단)
MERGE_DISTANCE_Y = 15          # 이 거리 이내의 수직 겹침은 병합
SUB_BAND_RATIO = 0.15          # 이미지 높이의 15% 이상인 밴드를 하위 분해

# v10: 구조적 앵커 관련 상수
STRUCTURAL_SIMILARITY_GATE = 0.25  # 이 이하면 "구조적으로 다른 화면" → 요소매칭 skip
ANCHOR_BG_TRANSITION_THRESH = 30   # 배경색 전환 감지 임계값 (RGB 거리)
ANCHOR_MIN_ZONE_H = 20            # 최소 존 높이 (px)


# ═══════════════════════════════════════════════════════════
# 적응형 콘텐츠 감지 (v5.2: 픽셀 단위 배경 추정)
# ═══════════════════════════════════════════════════════════

def _compute_adaptive_content(
    gray: np.ndarray,
    bg_diff_thresh: int = 18,
    canny_low: int = 25,
    canny_high: int = 80,
) -> np.ndarray:
    """
    픽셀 단위 로컬 배경 추정 기반 콘텐츠 마스크 생성.

    v5.1 문제: 행 가장자리 기반 로컬 bg가 오버레이 UI에서 실패.
    예) 라운드 바텀시트 — 가장자리는 어두운 채팅 배경, 중앙은 하얀 시트
    → 가장자리 bg=dark → 중앙 흰 배경이 전부 "콘텐츠"로 인식.

    v5.2 해결: cv2.medianBlur로 픽셀 단위 배경 추정 (background subtraction).
    - 대형 중앙값 필터 → 텍스트/아이콘을 제거하고 배경만 남김
    - 각 픽셀이 자기 주변 이웃의 중앙값과 비교 → 모든 배경 형태 대응
    - 오버레이, 라운드 모달, 그라데이션, 다중 배경 모두 정확

    이것은 구글 등에서 사용하는 표준 CV background subtraction 기법.

    Returns: 2D boolean content mask, shape (h, w)
    """
    h, w = gray.shape

    # 배경 추정: 대형 median blur (텍스트/아이콘을 제거하고 배경만 남김)
    # ksize > 가장 큰 UI 요소(아이콘 ~60px, 버튼 ~60px)보다 커야 함
    # 너무 작으면 아이콘 채우기가 배경으로 인식되어 감지 실패
    ksize = max(91, (min(h, w) // 4) | 1)  # 홀수 보장, 최소 91
    local_bg = cv2.medianBlur(gray, ksize).astype(np.float32)

    # 콘텐츠: 로컬 배경에서 충분히 다른 픽셀
    diff_from_bg = np.abs(gray.astype(np.float32) - local_bg)
    content_mask = diff_from_bg > bg_diff_thresh

    # Canny 에지 보완 (배경 무관, 미세 구조 감지)
    edges = cv2.Canny(gray, canny_low, canny_high)

    return content_mask | (edges > 0)


def _detect_status_bar_boundary(img: np.ndarray) -> int:
    """
    v11: 상단 영역에서 실제 상태바/노치 경계를 edge detection으로 탐지.

    고정 7% 대신, 상단 12% 내에서 강한 수평 에지(배경 전환, 헤더 구분선 등)를 찾는다.
    수평 에지가 없으면 fallback으로 고정 비율 사용.

    Returns: 상태바 아래쪽 y좌표 (cutoff)
    """
    h, w = img.shape[:2]
    scan_limit = int(h * 0.12)  # 상단 12% 스캔
    fallback = int(h * STATUS_BAR_RATIO)  # 기존 7% fallback

    if scan_limit < 20:
        return fallback

    # 상단 영역 grayscale + horizontal Sobel
    gray = cv2.cvtColor(img[:scan_limit], cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img[:scan_limit]
    # 수평 에지 감지 (Sobel Y방향 = 수평선)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    abs_sobel = np.abs(sobel_y)

    # 행별 수평 에지 강도
    row_edge = np.mean(abs_sobel, axis=1)

    # 최소 높이 20px 이후부터 탐색 (너무 위쪽은 노치 내부)
    min_y = max(20, int(h * 0.03))

    # 강한 수평 에지가 있는 행 찾기
    threshold = np.percentile(row_edge[min_y:], 85)  # 상위 15% 에지 강도
    if threshold < 5:  # 에지가 전혀 없으면 fallback
        return fallback

    # 가장 아래쪽의 강한 수평 에지 = 상태바/헤더 하단 경계
    candidates = []
    for y in range(min_y, scan_limit):
        if row_edge[y] >= threshold:
            candidates.append(y)

    if not candidates:
        return fallback

    # 연속된 에지 클러스터 중 가장 아래쪽 클러스터의 하단
    clusters = []
    cluster_start = candidates[0]
    prev = candidates[0]
    for y in candidates[1:]:
        if y - prev > 5:  # 5px 이상 떨어지면 새 클러스터
            clusters.append((cluster_start, prev))
            cluster_start = y
        prev = y
    clusters.append((cluster_start, prev))

    # 첫 번째 강한 에지 클러스터 = 상태바 하단 경계
    # (두 번째는 네비게이션 바일 수 있으므로 첫 번째만)
    boundary = clusters[0][1] + 1

    # 안전 범위: 3% ~ 10% 사이만 허용
    min_cutoff = int(h * 0.03)
    max_cutoff = int(h * 0.10)
    boundary = max(min_cutoff, min(max_cutoff, boundary))

    return boundary


def _trim_status_bar(bands: List[Dict], cutoff: int) -> List[Dict]:
    """상태바 영역(상단)에 걸치는 밴드를 제거하거나 트리밍."""
    result = []
    for b in bands:
        if b["y_end"] <= cutoff:
            continue  # 완전히 상태바 영역 → 제거
        if b["y_start"] < cutoff:
            # 상태바와 겹침 → 아래쪽만 유지
            b = dict(b)
            b["y_start"] = cutoff
            b["height"] = b["y_end"] - b["y_start"]
            b["center_y"] = (b["y_start"] + b["y_end"]) // 2
            if b["height"] < 10:
                continue  # 트리밍 후 너무 작으면 제거
        result.append(b)
    return result


def detect_and_compare(
    design_path: str,
    dev_path: str,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    두 이미지의 UI 구조를 감지하고 간격을 비교한다.

    v10: 구조적 앵커 기반 비교
    1. 사전 검증: 두 이미지가 비교 가능한 수준인지 판단
    2. 구조적 앵커 감지: 배경색 전환점 (콘텐츠 무관)
    3. 앵커 기반 존 매칭 → 존 내부 비교

    Returns:
        (differences, design_bands, dev_bands)
    """
    design = cv2.imread(design_path)
    dev = cv2.imread(dev_path)

    if design is None or dev is None:
        print("[ElementAnalyzer] 이미지 로드 실패")
        return [], [], []

    # ── Step 1: 스마트 정규화 ──
    target_w = dev.shape[1]
    if design.shape[1] != target_w:
        scale = target_w / design.shape[1]
        new_h = int(design.shape[0] * scale)
        design = cv2.resize(design, (target_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        print(f"[ElementAnalyzer] 디자인 리사이즈: {design.shape[1]}×{design.shape[0]}")

    compare_h = min(design.shape[0], dev.shape[0])
    design_crop = design[:compare_h]
    dev_crop = dev[:compare_h]
    target_h = compare_h

    print(f"[ElementAnalyzer] 비교 영역: {target_w}×{target_h}")

    # ── Step 1.5 (v10): 구조적 유사도 사전 검증 게이트 ──
    structural_sim = _check_structural_similarity(design_crop, dev_crop)
    print(f"[ElementAnalyzer] 구조적 유사도: {structural_sim:.3f} "
          f"(gate={STRUCTURAL_SIMILARITY_GATE})")

    skip_element_matching = structural_sim < STRUCTURAL_SIMILARITY_GATE

    if skip_element_matching:
        print(f"[ElementAnalyzer] ⚠ 구조적 유사도 낮음 ({structural_sim:.3f}) "
              f"→ 요소 단위 매칭 건너뜀 (오탐 방지)")

    # ── Step 2: 밴드 감지 ──
    design_bands = _detect_content_bands(design_crop, target_w, target_h, "design")
    dev_bands = _detect_content_bands(dev_crop, target_w, target_h, "dev")

    # ── Step 3: 상태바 제외 (v11: edge detection 기반) ──
    # 디자인/개발 각각에서 상태바 경계 감지 후 더 보수적인 값 사용
    design_cutoff = _detect_status_bar_boundary(design_crop)
    dev_cutoff = _detect_status_bar_boundary(dev_crop)
    status_cutoff = min(design_cutoff, dev_cutoff)  # 더 짧은 쪽 기준 (안전)
    design_bands = _trim_status_bar(design_bands, status_cutoff)
    dev_bands = _trim_status_bar(dev_bands, status_cutoff)
    print(f"[ElementAnalyzer] 상태바 제외(cutoff={status_cutoff}px, "
          f"design={design_cutoff}, dev={dev_cutoff}) 후: "
          f"디자인 {len(design_bands)}개, 개발 {len(dev_bands)}개")

    # ── Step 3.5: 대형 밴드 하위 분해 ──
    design_bands = _decompose_large_bands(design_bands, design_crop, target_w, target_h, "design")
    dev_bands = _decompose_large_bands(dev_bands, dev_crop, target_w, target_h, "dev")
    print(f"[ElementAnalyzer] 하위 분해 후: 디자인 {len(design_bands)}개, 개발 {len(dev_bands)}개")

    # ── Step 3.6: 밴드 경계 정밀 보정 (v4) ──
    design_bands = _refine_band_edges(design_bands, design_crop)
    dev_bands = _refine_band_edges(dev_bands, dev_crop)

    # ══════════════════════════════════════════════
    # v10: 구조 게이트 → 요소 단위 비교 (어젯밤 v8/v9 그대로)
    # ══════════════════════════════════════════════
    # 게이트 역할만: 구조적으로 너무 다르면 요소매칭 skip (오탐 방지)
    # 통과하면 기존 정밀 요소 매칭 그대로 실행

    if skip_element_matching:
        # ── 구조적으로 완전히 다른 화면 → CV 요소매칭 안 함 ──
        differences = []
        print(f"[ElementAnalyzer] 요소매칭 skip → 빈 결과 반환 (pixel diff/AI가 처리)")
    else:
        # ══════════════════════════════════════════════
        # v11: 요소 매칭 단일 경로 (갭 감지·밴드 매칭 제거)
        # ══════════════════════════════════════════════
        # 갭 감지는 콘텐츠 의존적 (언어 변경 → 줄바꿈 → 갭 위치 변동 → 오매칭)
        # 세밀 요소 매칭(kh=2)이 수직 간격 + 마진 + 높이 + 너비 모두 측정 가능

        design_elements = _detect_ui_elements(design_crop, exclude_top=status_cutoff)
        dev_elements = _detect_ui_elements(dev_crop, exclude_top=status_cutoff)
        print(f"[ElementAnalyzer] 요소 감지: 디자인 {len(design_elements)}개, "
              f"개발 {len(dev_elements)}개")

        elem_matches = _match_elements(
            design_elements, dev_elements, target_w, target_h,
            design_img=design_crop, dev_img=dev_crop,
        )

        differences = _compare_element_diffs(
            elem_matches, design_elements, dev_elements,
            dev_bands, target_w, target_h,
        )
        print(f"[ElementAnalyzer] 요소 차이: {len(differences)}개")

    # ── Step 7: 겹치는 차이 병합 ──
    differences = _merge_overlapping(differences)
    print(f"[ElementAnalyzer] 최종 차이: {len(differences)}개")

    return differences, design_bands, dev_bands


# ═══════════════════════════════════════════════════════════
# v10: 구조적 유사도 사전 검증 게이트
# ═══════════════════════════════════════════════════════════

def _check_structural_similarity(
    design_img: np.ndarray,
    dev_img: np.ndarray,
) -> float:
    """
    두 이미지의 구조적 유사도를 빠르게 판단.

    콘텐츠(텍스트)를 무시하고 구조(배경/레이아웃)만 비교:
    1. 강한 블러로 텍스트를 제거 → 배경+큰 구조만 남김
    2. 에지 감지로 UI 프레임워크 추출
    3. 두 구조 이미지의 SSIM 계산

    Returns: 0.0 ~ 1.0 (1.0 = 완전히 동일한 구조)
    """
    h, w = design_img.shape[:2]

    # 작은 크기로 리사이즈 (빠른 비교용)
    scale_h = min(h, 400)
    scale_w = int(w * scale_h / h)
    d_small = cv2.resize(design_img, (scale_w, scale_h))
    v_small = cv2.resize(dev_img, (scale_w, scale_h))

    # 강한 블러 → 텍스트/아이콘 제거, 배경+대형 구조만 남김
    ksize = max(31, scale_w // 8) | 1  # 홀수 보장
    d_blur = cv2.GaussianBlur(d_small, (ksize, ksize), 0)
    v_blur = cv2.GaussianBlur(v_small, (ksize, ksize), 0)

    # 그레이스케일 변환
    d_gray = cv2.cvtColor(d_blur, cv2.COLOR_BGR2GRAY)
    v_gray = cv2.cvtColor(v_blur, cv2.COLOR_BGR2GRAY)

    # 에지로 구조 프레임워크 추출
    d_edge = cv2.Canny(d_gray, 20, 60)
    v_edge = cv2.Canny(v_gray, 20, 60)

    # SSIM: 블러된 이미지의 구조 유사도 (텍스트 무관)
    win_size = min(7, scale_h - 1, scale_w - 1)
    if win_size % 2 == 0:
        win_size -= 1
    if win_size < 3:
        win_size = 3

    blur_ssim = ssim(d_gray, v_gray, win_size=win_size)

    # 에지 오버랩 비율 (구조적 프레임 일치도)
    d_edge_count = np.count_nonzero(d_edge)
    v_edge_count = np.count_nonzero(v_edge)
    if max(d_edge_count, v_edge_count) > 0:
        edge_overlap = np.count_nonzero(d_edge & v_edge)
        edge_sim = edge_overlap / max(d_edge_count, v_edge_count)
    else:
        edge_sim = 1.0

    # 색상 히스토그램 유사도 (전체 배경색 분포)
    d_hist = cv2.calcHist([d_blur], [0, 1, 2], None, [8, 8, 8],
                          [0, 256, 0, 256, 0, 256])
    v_hist = cv2.calcHist([v_blur], [0, 1, 2], None, [8, 8, 8],
                          [0, 256, 0, 256, 0, 256])
    cv2.normalize(d_hist, d_hist)
    cv2.normalize(v_hist, v_hist)
    hist_sim = max(0.0, cv2.compareHist(d_hist, v_hist, cv2.HISTCMP_CORREL))

    # 결합: 블러SSIM 40% + 에지유사도 30% + 색상분포 30%
    combined = blur_ssim * 0.40 + edge_sim * 0.30 + hist_sim * 0.30

    print(f"  [구조검증] blur_ssim={blur_ssim:.3f} edge_sim={edge_sim:.3f} "
          f"hist_sim={hist_sim:.3f} → combined={combined:.3f}")

    return combined


# ═══════════════════════════════════════════════════════════
# v10: 구조적 앵커 감지 (배경색 전환점)
# ═══════════════════════════════════════════════════════════

def _detect_bg_transition_anchors(
    img: np.ndarray,
    exclude_top: int = 0,
) -> List[int]:
    """
    배경색 전환점 + 콘텐츠 갭을 결합하여 구조적 앵커 Y좌표 목록 반환.

    두 가지 앵커 소스:
    1. 배경색 전환: 블러 후 행별 평균 RGB의 급격한 변화
    2. 콘텐츠 갭: 콘텐츠가 없는 수평 빈 영역의 중심

    두 소스 모두 콘텐츠(텍스트/아이콘) 변화에 강건:
    - 배경색: 텍스트를 블러로 제거하므로 무관
    - 콘텐츠 갭: 갭의 존재 자체가 구조적 특성 (텍스트 내용과 무관)
    """
    h, w = img.shape[:2]
    min_distance = max(ANCHOR_MIN_ZONE_H, h // 20)

    # ── 소스 1: 배경색 전환점 ──
    ksize = max(51, w // 6) | 1
    blurred = cv2.GaussianBlur(img, (ksize, ksize), 0)
    row_means = np.mean(blurred.astype(np.float32), axis=1)
    row_diffs = np.linalg.norm(np.diff(row_means, axis=0), axis=1)

    smooth_k = max(5, h // 50) | 1
    row_diffs_smooth = np.convolve(row_diffs, np.ones(smooth_k) / smooth_k, mode="same")

    bg_anchors = []
    for i in range(exclude_top, len(row_diffs_smooth)):
        if row_diffs_smooth[i] < ANCHOR_BG_TRANSITION_THRESH:
            continue
        window = 5
        local_start = max(0, i - window)
        local_end = min(len(row_diffs_smooth), i + window + 1)
        if row_diffs_smooth[i] == np.max(row_diffs_smooth[local_start:local_end]):
            if not bg_anchors or (i - bg_anchors[-1]) >= min_distance:
                bg_anchors.append(i)

    # ── 소스 2: 콘텐츠 갭 중심 (큰 갭만 = 섹션 구분) ──
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    content = _compute_adaptive_content(gray)
    row_density = np.mean(content.astype(np.float32), axis=1)

    EMPTY_THRESH = 0.015
    MIN_GAP_FOR_ANCHOR = max(8, h // 40)  # 큰 갭만 앵커로 사용

    gap_anchors = []
    gap_start = None
    for row in range(exclude_top, h):
        if row_density[row] < EMPTY_THRESH:
            if gap_start is None:
                gap_start = row
        else:
            if gap_start is not None:
                gap_h = row - gap_start
                if gap_h >= MIN_GAP_FOR_ANCHOR:
                    gap_center = (gap_start + row) // 2
                    gap_anchors.append(gap_center)
                gap_start = None

    # ── 두 소스 결합 + 거리 필터링 ──
    all_anchors = sorted(set(bg_anchors + gap_anchors))

    # 너무 가까운 앵커 병합
    merged = []
    for a in all_anchors:
        if not merged or (a - merged[-1]) >= min_distance:
            merged.append(a)

    return merged


def _split_into_zones(
    anchors: List[int],
    img_h: int,
    exclude_top: int = 0,
) -> List[Dict]:
    """
    앵커 Y좌표로 이미지를 존(zone)으로 분할.

    Returns: [{"y_start", "y_end", "height", "center_y"}, ...]
    """
    boundaries = [exclude_top] + anchors + [img_h]
    zones = []

    for i in range(len(boundaries) - 1):
        y_start = boundaries[i]
        y_end = boundaries[i + 1]
        zone_h = y_end - y_start

        if zone_h < ANCHOR_MIN_ZONE_H:
            continue

        zones.append({
            "y_start": y_start,
            "y_end": y_end,
            "height": zone_h,
            "center_y": (y_start + y_end) // 2,
        })

    return zones


# ═══════════════════════════════════════════════════════════
# v10: 앵커 기반 존 비교
# ═══════════════════════════════════════════════════════════

def _anchor_based_zone_compare(
    design_img: np.ndarray,
    dev_img: np.ndarray,
    img_w: int,
    img_h: int,
    exclude_top: int,
    dev_bands: List[Dict],
) -> List[Dict]:
    """
    배경색 앵커로 나눈 존(zone) 단위로 구조적 차이만 비교.

    콘텐츠(텍스트)에 무관하게:
    1. 배경색 전환점 감지 → 존 분할
    2. 디자인/개발 존을 매칭 (배경색 유사도 기반)
    3. 매칭된 존의 높이 차이 = 구조적 간격 차이
    """
    # 앵커 감지
    d_anchors = _detect_bg_transition_anchors(design_img, exclude_top)
    v_anchors = _detect_bg_transition_anchors(dev_img, exclude_top)
    print(f"  [앵커v10] 디자인 앵커: {d_anchors}")
    print(f"  [앵커v10] 개발 앵커: {v_anchors}")

    # 존 분할
    d_zones = _split_into_zones(d_anchors, img_h, exclude_top)
    v_zones = _split_into_zones(v_anchors, img_h, exclude_top)
    print(f"  [앵커v10] 존: 디자인 {len(d_zones)}개, 개발 {len(v_zones)}개")

    if not d_zones or not v_zones:
        return []

    # 존 매칭: 배경색 유사도 + 상대 위치 (DP 순서 보존)
    matches = _match_zones(d_zones, v_zones, design_img, dev_img, img_h)

    # 매칭된 존 간 차이 생성
    diffs = _compare_zone_diffs(matches, d_zones, v_zones, dev_bands, img_w, img_h)

    print(f"  [앵커v10] 존 비교 → {len(diffs)}개 구조적 차이")
    return diffs


def _zone_bg_color(img: np.ndarray, zone: Dict) -> np.ndarray:
    """존 영역의 대표 배경색 (블러 후 중앙부 평균)."""
    y1, y2 = zone["y_start"], zone["y_end"]
    region = img[y1:y2, :]

    # 강한 블러로 텍스트 제거
    ksize = max(31, region.shape[1] // 4) | 1
    blurred = cv2.GaussianBlur(region, (ksize, ksize), 0)

    # 중앙 50% 영역의 평균색 (가장자리 노이즈 제외)
    h, w = blurred.shape[:2]
    margin_x = w // 4
    margin_y = h // 4
    center = blurred[margin_y:h - margin_y, margin_x:w - margin_x]
    if center.size == 0:
        center = blurred

    return np.mean(center.astype(np.float32), axis=(0, 1))


def _match_zones(
    d_zones: List[Dict],
    v_zones: List[Dict],
    design_img: np.ndarray,
    dev_img: np.ndarray,
    img_h: int,
) -> List[Tuple[int, int, float]]:
    """
    존을 배경색 유사도 + 상대 위치로 매칭 (DP 순서 보존).
    """
    n_d = len(d_zones)
    n_v = len(v_zones)

    # 배경색 계산
    d_colors = [_zone_bg_color(design_img, z) for z in d_zones]
    v_colors = [_zone_bg_color(dev_img, z) for z in v_zones]

    # 유사도 매트릭스
    score_matrix = np.zeros((n_d, n_v))
    for di in range(n_d):
        for vi in range(n_v):
            # 배경색 유사도 (RGB 거리 → 0~1)
            color_dist = float(np.linalg.norm(d_colors[di] - v_colors[vi]))
            color_sim = max(0.0, 1.0 - color_dist / 200.0)

            # 상대 위치 유사도
            d_rel = d_zones[di]["center_y"] / img_h
            v_rel = v_zones[vi]["center_y"] / img_h
            pos_sim = max(0.0, 1.0 - abs(d_rel - v_rel) * 4)

            # 높이 비율 유사도
            h_ratio = min(d_zones[di]["height"], v_zones[vi]["height"]) / \
                      max(d_zones[di]["height"], v_zones[vi]["height"], 1)

            # 결합: 배경색 50% + 위치 30% + 높이 20%
            score_matrix[di, vi] = color_sim * 0.50 + pos_sim * 0.30 + h_ratio * 0.20

    # DP 순서 보존 매칭
    MIN_ZONE_SCORE = 0.35
    dp = np.zeros((n_d + 1, n_v + 1))
    choice = [[None] * (n_v + 1) for _ in range(n_d + 1)]

    for di in range(1, n_d + 1):
        for vi in range(1, n_v + 1):
            skip_d = dp[di - 1][vi]
            skip_v = dp[di][vi - 1]
            match_s = dp[di - 1][vi - 1] + score_matrix[di - 1][vi - 1]

            best = max(skip_d, skip_v, match_s)
            dp[di][vi] = best

            if best == match_s and score_matrix[di - 1][vi - 1] >= MIN_ZONE_SCORE:
                choice[di][vi] = "match"
            elif best == skip_d:
                choice[di][vi] = "skip_d"
            else:
                choice[di][vi] = "skip_v"

    # 역추적
    matches = []  # type: List[Tuple[int, int, float]]
    di, vi = n_d, n_v
    while di > 0 and vi > 0:
        if choice[di][vi] == "match":
            matches.append((di - 1, vi - 1, float(score_matrix[di - 1][vi - 1])))
            di -= 1
            vi -= 1
        elif choice[di][vi] == "skip_d":
            di -= 1
        else:
            vi -= 1
    matches.reverse()

    for d_i, v_i, sc in matches:
        print(f"    존매칭: D[{d_i}](y={d_zones[d_i]['y_start']}~{d_zones[d_i]['y_end']}) "
              f"↔ V[{v_i}](y={v_zones[v_i]['y_start']}~{v_zones[v_i]['y_end']}) "
              f"score={sc:.2f}")

    return matches


def _compare_zone_diffs(
    matches: List[Tuple[int, int, float]],
    d_zones: List[Dict],
    v_zones: List[Dict],
    dev_bands: List[Dict],
    img_w: int,
    img_h: int,
) -> List[Dict]:
    """
    매칭된 존 간의 구조적 차이를 생성.

    존 높이 차이 = 섹션 높이 차이 (콘텐츠 무관한 구조적 측정)
    연속 존 간 갭 차이 = 섹션 간 간격 차이
    """
    diffs = []  # type: List[Dict]

    # 고신뢰도 매칭만 사용
    confident = [(d, v, s) for d, v, s in matches if s >= 0.50]

    # ── 1. 존 높이 차이 ──
    for d_idx, v_idx, score in confident:
        dz = d_zones[d_idx]
        vz = v_zones[v_idx]
        h_diff = abs(dz["height"] - vz["height"])

        if h_diff < MIN_HEIGHT_DIFF:
            continue

        # 높이 비율 체크 — 3배 이상 차이나면 다른 존
        h_ratio = min(dz["height"], vz["height"]) / max(dz["height"], vz["height"], 1)
        if h_ratio < 0.33:
            continue

        band_idx = _find_containing_band_idx(
            {"center_y": vz["center_y"]}, dev_bands
        )

        diffs.append({
            "type": "element_height",
            "severity": _proportional_severity(h_diff, max(dz["height"], vz["height"], 1)),
            "design_value": f"{dz['height']}px",
            "dev_value": f"{vz['height']}px",
            "diff_px": h_diff,
            "band_above_idx": band_idx,
            "band_below_idx": band_idx,
            "bbox_x": 0, "bbox_y": vz["y_start"],
            "bbox_w": img_w, "bbox_h": vz["height"],
            "design_bbox_x": 0, "design_bbox_y": dz["y_start"],
            "design_bbox_w": img_w, "design_bbox_h": dz["height"],
        })

    # ── 2. 연속 존 간 간격 차이 ──
    by_y = sorted(confident, key=lambda m: d_zones[m[0]]["y_start"])

    for i in range(len(by_y) - 1):
        d_a, v_a, _sa = by_y[i]
        d_b, v_b, _sb = by_y[i + 1]

        d_gap = d_zones[d_b]["y_start"] - d_zones[d_a]["y_end"]
        v_gap = v_zones[v_b]["y_start"] - v_zones[v_a]["y_end"]

        if d_gap < 0 or v_gap < 0:
            continue

        gap_diff = abs(d_gap - v_gap)
        if gap_diff < MIN_SPACING_DIFF:
            continue

        # 갭 비율 안전장치
        max_gap = max(d_gap, v_gap)
        min_gap = min(d_gap, v_gap)
        if max_gap > 0 and min_gap == 0 and max_gap > img_h * 0.05:
            continue
        if min_gap > 0 and max_gap / min_gap > 5:
            continue

        gap_center_y = (v_zones[v_a]["y_end"] + v_zones[v_b]["y_start"]) / 2
        if gap_center_y < img_h * 0.1:
            gap_type = "top_margin"
        elif gap_center_y > img_h * 0.92:
            gap_type = "bottom_margin"
        else:
            gap_type = "vertical_spacing"

        above_band = _find_containing_band_idx(
            {"center_y": v_zones[v_a]["center_y"]}, dev_bands
        )
        below_band = _find_containing_band_idx(
            {"center_y": v_zones[v_b]["center_y"]}, dev_bands
        )

        diffs.append({
            "type": gap_type,
            "severity": _proportional_severity(gap_diff, max(d_gap, v_gap, 1)),
            "design_value": f"{d_gap}px",
            "dev_value": f"{v_gap}px",
            "diff_px": gap_diff,
            "band_above_idx": above_band,
            "band_below_idx": below_band,
            "bbox_x": 0,
            "bbox_y": v_zones[v_a]["y_end"],
            "bbox_w": img_w,
            "bbox_h": max(v_gap, 1),
            "design_bbox_x": 0,
            "design_bbox_y": d_zones[d_a]["y_end"],
            "design_bbox_w": img_w,
            "design_bbox_h": max(d_gap, 1),
        })

    # 심각도 → 위치 순 정렬
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    diffs.sort(key=lambda d: (sev_order.get(d["severity"], 2), d["bbox_y"]))

    return diffs


def _merge_anchor_and_element_diffs(
    anchor_diffs: List[Dict],
    elem_diffs: List[Dict],
    img_h: int,
) -> List[Dict]:
    """
    앵커 diff와 요소 diff를 결합, Y범위 겹침 중복 제거.

    원칙: 같은 영역이면 요소 diff가 더 정밀하므로 요소 diff 우선.
    앵커 diff는 요소 매칭이 놓친 구조적 차이를 보완.
    """
    if not anchor_diffs:
        return elem_diffs
    if not elem_diffs:
        return anchor_diffs

    # 요소 diff의 Y 범위 수집
    elem_ys = [(d["bbox_y"], d["bbox_y"] + d["bbox_h"]) for d in elem_diffs]

    # 앵커 diff 중 요소 diff와 겹치지 않는 것만 추가
    filtered_anchors = []
    for ad in anchor_diffs:
        ay1 = ad["bbox_y"]
        ay2 = ay1 + ad["bbox_h"]
        is_covered = False

        for ey1, ey2 in elem_ys:
            overlap_start = max(ay1, ey1)
            overlap_end = min(ay2, ey2)
            if overlap_end > overlap_start:
                overlap = overlap_end - overlap_start
                ad_h = ay2 - ay1
                if ad_h > 0 and overlap / ad_h > 0.5:
                    is_covered = True
                    break

        if not is_covered:
            filtered_anchors.append(ad)

    return elem_diffs + filtered_anchors


# ═══════════════════════════════════════════════════════════
# 밴드 감지 (v2: 강화된 임계값 + 노이즈 필터링)
# ═══════════════════════════════════════════════════════════

def _detect_content_bands(
    img: np.ndarray, img_w: int, img_h: int, label: str = ""
) -> List[Dict]:
    """Horizontal Projection Profile로 콘텐츠 밴드를 감지."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # v5.1: 적응형 로컬 배경 콘텐츠 감지 (다중 배경색 대응)
    combined = _compute_adaptive_content(gray, bg_diff_thresh=20, canny_low=30, canny_high=90)

    # Horizontal Projection
    h_proj = np.mean(combined.astype(np.float32), axis=1)

    # 적응형 스무딩 (v2: 더 강한 스무딩으로 노이즈 제거)
    smooth_k = max(5, h // 100)
    if smooth_k % 2 == 0:
        smooth_k += 1
    h_proj = np.convolve(h_proj, np.ones(smooth_k) / smooth_k, mode="same")

    # 밴드 추출 (v2: 높아진 임계값)
    MIN_BAND_H = max(10, h // 50)   # v1: max(4, h // 80) — 최소 높이 상향
    MIN_GAP_H = max(4, h // 80)     # v1: max(2, h // 120) — 최소 간격 상향

    # v11: 적응형 콘텐츠 임계값 — 이미지별 최적 threshold 자동 계산
    if CONTENT_THRESH_ADAPTIVE:
        nonzero = h_proj[h_proj > 0.001]  # 완전 빈 행 제외
        if len(nonzero) > 20:
            adaptive_thresh = float(np.percentile(nonzero, 30))  # 30th percentile
            # 안전 범위: 0.01 ~ 0.05 (너무 민감하거나 둔감하지 않게)
            content_thresh = max(0.01, min(0.05, adaptive_thresh))
        else:
            content_thresh = CONTENT_THRESH
        if label:
            print(f"  [{label}] 적응형 콘텐츠 임계값: {content_thresh:.4f}")
    else:
        content_thresh = CONTENT_THRESH

    is_content = h_proj > content_thresh

    bands = []
    band_start = None

    for row in range(h):
        if is_content[row] and band_start is None:
            band_start = row
        elif not is_content[row] and band_start is not None:
            if row - band_start >= MIN_BAND_H:
                bands.append({"y_start": band_start, "y_end": row})
            band_start = None

    if band_start is not None and h - band_start >= MIN_BAND_H:
        bands.append({"y_start": band_start, "y_end": h})

    # 가까운 밴드 병합
    merged = []
    for band in bands:
        if merged and band["y_start"] - merged[-1]["y_end"] < MIN_GAP_H:
            merged[-1]["y_end"] = band["y_end"]
        else:
            merged.append(dict(band))

    # 세부 측정
    for band in merged:
        y1, y2 = band["y_start"], band["y_end"]
        band["height"] = y2 - y1
        band["center_y"] = (y1 + y2) // 2

        band_content = combined[y1:y2, :]
        v_proj = np.mean(band_content.astype(np.float32), axis=0)

        band["left_margin"] = 0
        for col in range(w):
            if v_proj[col] > 0.03:  # v1: 0.02
                band["left_margin"] = col
                break

        band["right_margin"] = 0
        for col in range(w - 1, -1, -1):
            if v_proj[col] > 0.03:
                band["right_margin"] = (w - 1) - col
                break

        band["content_width"] = w - band["left_margin"] - band["right_margin"]
        band["density"] = float(np.mean(band_content))

    if label:
        for i, b in enumerate(merged):
            print(f"  [{label}] 밴드 {i}: y={b['y_start']}~{b['y_end']} "
                  f"(h={b['height']}) L={b['left_margin']} R={b['right_margin']}")

    return merged


# ═══════════════════════════════════════════════════════════
# 대형 밴드 하위 분해 (v3)
# ═══════════════════════════════════════════════════════════

def _detect_sub_bands(img: np.ndarray, img_w: int, img_h: int) -> List[Dict]:
    """세밀한 임계값으로 하위 밴드를 감지 (대형 밴드 내부용)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # v5.1: 적응형 로컬 배경 (더 민감한 임계값)
    combined = _compute_adaptive_content(gray, bg_diff_thresh=15, canny_low=25, canny_high=80)

    h_proj = np.mean(combined.astype(np.float32), axis=1)

    smooth_k = max(3, h // 60)
    if smooth_k % 2 == 0:
        smooth_k += 1
    h_proj = np.convolve(h_proj, np.ones(smooth_k) / smooth_k, mode="same")

    MIN_BAND_H = max(8, h // 30)             # 더 작은 밴드도 감지
    MIN_GAP_H = max(3, h // 50)              # 더 좁은 갭도 인식
    is_content = h_proj > 0.02               # 더 민감 (전체: 0.025)

    bands: List[Dict] = []
    band_start = None

    for row in range(h):
        if is_content[row] and band_start is None:
            band_start = row
        elif not is_content[row] and band_start is not None:
            if row - band_start >= MIN_BAND_H:
                bands.append({"y_start": band_start, "y_end": row})
            band_start = None

    if band_start is not None and h - band_start >= MIN_BAND_H:
        bands.append({"y_start": band_start, "y_end": h})

    merged: List[Dict] = []
    for band in bands:
        if merged and band["y_start"] - merged[-1]["y_end"] < MIN_GAP_H:
            merged[-1]["y_end"] = band["y_end"]
        else:
            merged.append(dict(band))

    for band in merged:
        y1, y2 = band["y_start"], band["y_end"]
        band["height"] = y2 - y1
        band["center_y"] = (y1 + y2) // 2

        band_content = combined[y1:y2, :]
        v_proj = np.mean(band_content.astype(np.float32), axis=0)

        band["left_margin"] = 0
        for col in range(w):
            if v_proj[col] > 0.03:
                band["left_margin"] = col
                break

        band["right_margin"] = 0
        for col in range(w - 1, -1, -1):
            if v_proj[col] > 0.03:
                band["right_margin"] = (w - 1) - col
                break

        band["content_width"] = w - band["left_margin"] - band["right_margin"]
        band["density"] = float(np.mean(band_content))

    return merged


def _decompose_large_bands(
    bands: List[Dict], img: np.ndarray, img_w: int, img_h: int, label: str = ""
) -> List[Dict]:
    """이미지 높이의 15% 이상인 대형 밴드를 하위 요소로 분해."""
    max_h = int(img_h * SUB_BAND_RATIO)
    result: List[Dict] = []

    for band in bands:
        if band["height"] <= max_h:
            result.append(band)
            continue

        y1, y2 = band["y_start"], band["y_end"]
        sub_img = img[y1:y2, :]
        sub_h = y2 - y1

        sub_bands = _detect_sub_bands(sub_img, img_w, sub_h)

        if len(sub_bands) >= 2:
            for sb in sub_bands:
                sb["y_start"] += y1
                sb["y_end"] += y1
                sb["center_y"] = (sb["y_start"] + sb["y_end"]) // 2
            result.extend(sub_bands)
            if label:
                print(f"  [{label}] 대형 밴드(y={y1}~{y2}, h={band['height']}) "
                      f"→ {len(sub_bands)}개 하위 밴드로 분해")
        else:
            result.append(band)

    return result


# ═══════════════════════════════════════════════════════════
# 밴드 경계 정밀 보정 (v4)
# ═══════════════════════════════════════════════════════════

def _refine_band_edges(bands: List[Dict], img: np.ndarray) -> List[Dict]:
    """
    밴드의 y_start/y_end를 실제 콘텐츠 픽셀 경계로 정밀 보정.

    수평 프로젝션의 스무딩/임계값 때문에 밴드 경계가 실제 콘텐츠보다
    위/아래로 확장될 수 있다. 이를 콘텐츠의 첫/마지막 행으로 조정하여
    간격 계산과 bbox 생성의 정확도를 높인다.
    """
    if not bands:
        return bands

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # v5.1: 적응형 로컬 배경 기반 콘텐츠 감지
    content_mask = _compute_adaptive_content(gray, bg_diff_thresh=25, canny_low=40, canny_high=100)
    combined = np.mean(content_mask.astype(np.float32), axis=1)

    EDGE_THRESH = 0.025  # 행의 2.5% 이상 콘텐츠 = 콘텐츠 행

    refined_count = 0
    for band in bands:
        y1, y2 = band["y_start"], band["y_end"]
        band_h = y2 - y1
        max_trim = min(band_h // 4, 30)  # 각 방향 최대 25% 또는 30px

        # y_start 보정: 첫 콘텐츠 행 찾기
        new_y1 = y1
        for row in range(y1, min(y2, y1 + max_trim)):
            if combined[row] >= EDGE_THRESH:
                new_y1 = row
                break

        # y_end 보정: 마지막 콘텐츠 행 찾기
        new_y2 = y2
        for row in range(y2 - 1, max(y1, y2 - max_trim) - 1, -1):
            if combined[row] >= EDGE_THRESH:
                new_y2 = row + 1
                break

        if new_y2 - new_y1 >= 8:
            if new_y1 != y1 or new_y2 != y2:
                refined_count += 1
            band["y_start"] = new_y1
            band["y_end"] = new_y2
            band["height"] = new_y2 - new_y1
            band["center_y"] = (new_y1 + new_y2) // 2

    return bands


# ═══════════════════════════════════════════════════════════
# 갭 중심(Gap-Centric) 간격 감지 (v5)
# ═══════════════════════════════════════════════════════════

def _detect_horizontal_gaps(
    img: np.ndarray, img_h: int, exclude_top: int = 0
) -> List[Dict]:
    """
    이미지에서 모든 수평 빈 갭(연속 빈 행)을 직접 감지.

    밴드(콘텐츠) 경계에서 간격을 유도하는 방식의 근본적 한계를 극복:
    - 밴드 경계: 스무딩/임계값 의존 → 부정확할 수 있음
    - 갭 경계: 빈 행 vs 콘텐츠 행의 명확한 이진 판정 → 항상 정확

    bbox = 갭 자체 → 콘텐츠를 포함할 수 없음 (구조적 보장).

    Returns: [{"y_start", "y_end", "height", "center_y"}, ...]
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # v5.1: 적응형 로컬 배경 콘텐츠 감지 (다중 배경색 대응)
    combined = _compute_adaptive_content(gray, bg_diff_thresh=18, canny_low=25, canny_high=80)

    row_density = np.mean(combined.astype(np.float32), axis=1)

    # 빈 행 판정 — 행의 1.5% 미만이 콘텐츠면 빈 행 (매우 민감)
    EMPTY_THRESH = 0.015
    MIN_GAP_H = 4  # 최소 4px 갭

    is_empty = row_density < EMPTY_THRESH

    gaps: List[Dict] = []
    gap_start = None

    scan_start = max(0, exclude_top)
    scan_end = min(h, img_h)

    for row in range(scan_start, scan_end):
        if is_empty[row]:
            if gap_start is None:
                gap_start = row
        else:
            if gap_start is not None:
                gap_h = row - gap_start
                if gap_h >= MIN_GAP_H:
                    gaps.append({
                        "y_start": gap_start,
                        "y_end": row,
                        "height": gap_h,
                        "center_y": (gap_start + row) // 2,
                    })
                gap_start = None

    # 이미지 끝까지 빈 영역
    if gap_start is not None and scan_end - gap_start >= MIN_GAP_H:
        gaps.append({
            "y_start": gap_start,
            "y_end": scan_end,
            "height": scan_end - gap_start,
            "center_y": (gap_start + scan_end) // 2,
        })

    return gaps


def _match_gaps_by_position(
    design_gaps: List[Dict],
    dev_gaps: List[Dict],
    img_h: int,
) -> List[Tuple[int, int, float]]:
    """
    디자인/개발 갭을 상대 위치 기반으로 매칭.
    순서 보존 DP (밴드 매칭과 동일한 접근).
    """
    if not design_gaps or not dev_gaps:
        return []

    n_d = len(design_gaps)
    n_v = len(dev_gaps)

    # 유사도 매트릭스: 위치 70% + 높이 30%
    score_matrix = np.zeros((n_d, n_v))
    for di in range(n_d):
        d_rel = design_gaps[di]["center_y"] / img_h
        for vi in range(n_v):
            v_rel = dev_gaps[vi]["center_y"] / img_h
            pos_sim = max(0.0, 1.0 - abs(d_rel - v_rel) * 5)
            h_ratio = min(design_gaps[di]["height"], dev_gaps[vi]["height"]) / \
                      max(design_gaps[di]["height"], dev_gaps[vi]["height"], 1)
            score_matrix[di, vi] = pos_sim * 0.7 + h_ratio * 0.3

    # DP 순서 보존 매칭
    MIN_SCORE = 0.3
    dp = np.zeros((n_d + 1, n_v + 1))
    choice = [[None] * (n_v + 1) for _ in range(n_d + 1)]

    for di in range(1, n_d + 1):
        for vi in range(1, n_v + 1):
            skip_d = dp[di - 1][vi]
            skip_v = dp[di][vi - 1]
            match_s = dp[di - 1][vi - 1] + score_matrix[di - 1][vi - 1]

            best = max(skip_d, skip_v, match_s)
            dp[di][vi] = best

            if best == match_s and score_matrix[di - 1][vi - 1] >= MIN_SCORE:
                choice[di][vi] = "match"
            elif best == skip_d:
                choice[di][vi] = "skip_d"
            else:
                choice[di][vi] = "skip_v"

    matches: List[Tuple[int, int]] = []
    di, vi = n_d, n_v
    while di > 0 and vi > 0:
        if choice[di][vi] == "match":
            matches.append((di - 1, vi - 1))
            di -= 1
            vi -= 1
        elif choice[di][vi] == "skip_d":
            di -= 1
        else:
            vi -= 1

    matches.reverse()

    # 매칭 점수를 포함하여 반환 (품질 필터링용)
    scored: List[Tuple[int, int, float]] = []
    for di_idx, vi_idx in matches:
        s = score_matrix[di_idx][vi_idx]
        scored.append((di_idx, vi_idx, s))
    return scored


def _find_adjacent_band_idx(
    gap: Dict, bands: List[Dict]
) -> Tuple[int, int]:
    """갭의 위/아래에 인접한 밴드 인덱스를 반환."""
    above_idx = -1
    below_idx = -1

    for i, band in enumerate(bands):
        if band["y_end"] <= gap["y_start"] + 5:
            above_idx = i  # 갭 위의 마지막 밴드
        if band["y_start"] >= gap["y_end"] - 5 and below_idx == -1:
            below_idx = i  # 갭 아래의 첫 밴드

    return above_idx, below_idx


def _compare_gap_spacings(
    gap_matches: List[Tuple[int, int, float]],
    design_gaps: List[Dict],
    dev_gaps: List[Dict],
    dev_bands: List[Dict],
    img_w: int,
    img_h: int,
) -> List[Dict]:
    """
    매칭된 갭 쌍의 높이를 비교하여 간격 차이를 생성.

    핵심: bbox = 갭 그 자체 → 콘텐츠를 절대 포함하지 않음.
    이것이 밴드-기반 간격 감지를 대체하는 이유.

    v5.3: 갭 매칭도 품질 필터링 적용
    """
    diffs: List[Dict] = []

    for d_idx, v_idx, score in gap_matches:
        if score < MATCH_HIGH_CONFIDENCE:
            print(f"  [갭필터] skip: D[{d_idx}]↔V[{v_idx}] score={score:.2f}")
            continue
        d_gap = design_gaps[d_idx]
        v_gap = dev_gaps[v_idx]

        height_diff = abs(d_gap["height"] - v_gap["height"])
        if height_diff < MIN_SPACING_DIFF:
            continue

        # 갭 유형 결정: 위치 기반
        is_top = v_gap["y_start"] < img_h * 0.1
        is_bottom = v_gap["y_end"] > img_h * 0.92

        if is_top:
            diff_type = "top_margin"
        elif is_bottom:
            diff_type = "bottom_margin"
        else:
            diff_type = "vertical_spacing"

        # 라벨링용: 갭 인접 밴드 인덱스
        above_idx, below_idx = _find_adjacent_band_idx(v_gap, dev_bands)

        diffs.append({
            "type": diff_type,
            "severity": _proportional_severity(
                height_diff, max(d_gap["height"], v_gap["height"], 1)
            ),
            "design_value": f"{d_gap['height']}px",
            "dev_value": f"{v_gap['height']}px",
            "diff_px": height_diff,
            "band_above_idx": above_idx,
            "band_below_idx": below_idx,
            # bbox = 갭 자체 (항상 정확 — 구조적 보장)
            "bbox_x": 0,
            "bbox_y": v_gap["y_start"],
            "bbox_w": img_w,
            "bbox_h": v_gap["height"],
            "design_bbox_x": 0,
            "design_bbox_y": d_gap["y_start"],
            "design_bbox_w": img_w,
            "design_bbox_h": d_gap["height"],
        })

    # 심각도 → 위치 순 정렬
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    diffs.sort(key=lambda d: (sev_order.get(d["severity"], 2), d["bbox_y"]))
    return diffs


# ═══════════════════════════════════════════════════════════
# 밴드 매칭 v2: 시각적 유사도 + 순서 보존
# ═══════════════════════════════════════════════════════════

def _band_histogram(img: np.ndarray, band: Dict) -> np.ndarray:
    """밴드 영역의 색상 히스토그램을 계산."""
    region = img[band["y_start"]:band["y_end"], :]
    hist = cv2.calcHist([region], [0, 1, 2], None, [8, 8, 8],
                        [0, 256, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten()


def _match_bands_visual(
    design_bands: List[Dict],
    dev_bands: List[Dict],
    design_img: np.ndarray,
    dev_img: np.ndarray,
    img_h: int,
) -> List[Tuple[int, int, float]]:
    """
    시각적 유사도 + 위치 + 높이를 결합한 밴드 매칭.
    순서를 보존하면서 최적의 매칭을 찾는다.
    """
    if not design_bands or not dev_bands:
        return []

    n_d = len(design_bands)
    n_v = len(dev_bands)

    # ── 유사도 매트릭스 계산 ──
    # 히스토그램 미리 계산
    d_hists = [_band_histogram(design_img, b) for b in design_bands]
    v_hists = [_band_histogram(dev_img, b) for b in dev_bands]

    score_matrix = np.zeros((n_d, n_v))

    for di in range(n_d):
        db = design_bands[di]
        for vi in range(n_v):
            vb = dev_bands[vi]

            # 시각적 유사도 (히스토그램 상관)
            visual_sim = cv2.compareHist(d_hists[di], v_hists[vi], cv2.HISTCMP_CORREL)
            visual_sim = max(0.0, visual_sim)  # 음수 → 0

            # 위치 유사도 (상대 위치 기반)
            d_rel = db["center_y"] / img_h
            v_rel = vb["center_y"] / img_h
            pos_sim = max(0.0, 1.0 - abs(d_rel - v_rel) * 4)

            # 높이 유사도
            h_ratio = min(db["height"], vb["height"]) / max(db["height"], vb["height"], 1)

            # 결합 점수: 시각 40% + 위치 30% + 높이 30%
            score_matrix[di, vi] = visual_sim * 0.4 + pos_sim * 0.3 + h_ratio * 0.3

    # ── 순서 보존 매칭 (DP 기반) ──
    # dp[i][j] = design[:i+1]와 dev[:j+1]에서의 최대 매칭 점수 합
    dp = np.zeros((n_d + 1, n_v + 1))
    choice = [[None] * (n_v + 1) for _ in range(n_d + 1)]

    for di in range(1, n_d + 1):
        for vi in range(1, n_v + 1):
            # 옵션 1: 이 쌍을 매칭하지 않음
            skip_d = dp[di - 1][vi]
            skip_v = dp[di][vi - 1]

            # 옵션 2: 이 쌍을 매칭
            match_score = dp[di - 1][vi - 1] + score_matrix[di - 1][vi - 1]

            best = max(skip_d, skip_v, match_score)
            dp[di][vi] = best

            if best == match_score and score_matrix[di - 1][vi - 1] >= MATCH_MIN_SCORE:
                choice[di][vi] = "match"
            elif best == skip_d:
                choice[di][vi] = "skip_d"
            else:
                choice[di][vi] = "skip_v"

    # 역추적으로 매칭 쌍 추출
    matches = []
    di, vi = n_d, n_v
    while di > 0 and vi > 0:
        if choice[di][vi] == "match":
            matches.append((di - 1, vi - 1))
            di -= 1
            vi -= 1
        elif choice[di][vi] == "skip_d":
            di -= 1
        else:
            vi -= 1

    matches.reverse()

    # 매칭 점수를 포함하여 반환 (품질 필터링용)
    scored_matches: List[Tuple[int, int, float]] = []
    for d_idx, v_idx in matches:
        s = score_matrix[d_idx][v_idx]
        scored_matches.append((d_idx, v_idx, s))
        print(f"  매칭: design[{d_idx}] ↔ dev[{v_idx}] (score={s:.2f})")

    return scored_matches


# ═══════════════════════════════════════════════════════════
# 차이 비교 (v2: 높은 임계값 + 비례적 심각도)
# ═══════════════════════════════════════════════════════════

def _compare_margins_and_heights(
    matches: List[Tuple[int, int, float]],
    design_bands: List[Dict],
    dev_bands: List[Dict],
    img_w: int,
    img_h: int,
) -> List[Dict]:
    """
    매칭된 밴드 쌍의 마진과 높이만 비교 (수직 간격은 갭 중심 감지가 처리).

    v5: vertical_spacing, top_margin, bottom_margin 제거
        → _compare_gap_spacings()가 갭 직접 감지로 대체 (bbox 100% 정확)

    v5.3: 매칭 품질 필터링 추가
        — 낮은 신뢰도 매칭(score < MATCH_HIGH_CONFIDENCE)은 건너뜀
        — 밴드 크기 비율이 너무 다른 매칭(ratio < MIN_BAND_SIZE_RATIO)은 건너뜀
        — AI 경로(Gemini)가 나머지를 담당
    """
    differences = []

    sorted_matches = sorted(matches, key=lambda m: design_bands[m[0]]["center_y"])

    # ── 0. 품질 필터링: 신뢰도 낮은 매칭 제거 ──
    # 구글 엔지니어 접근: CV diff는 보수적으로 — 확실한 것만 보고, 나머지는 AI에 위임
    high_confidence = []
    for match_tuple in sorted_matches:
        d_idx, v_idx, score = match_tuple
        db = design_bands[d_idx]
        vb = dev_bands[v_idx]
        size_ratio = min(db["height"], vb["height"]) / max(db["height"], vb["height"], 1)

        # 콘텐츠 너비 비율: 마진이 완전히 다른 밴드 = 다른 요소
        d_cw = max(img_w - db["left_margin"] - db["right_margin"], 1)
        v_cw = max(img_w - vb["left_margin"] - vb["right_margin"], 1)
        cw_ratio = min(d_cw, v_cw) / max(d_cw, v_cw, 1)

        if score < MATCH_HIGH_CONFIDENCE:
            print(f"  [품질필터] skip: D[{d_idx}]↔V[{v_idx}] "
                  f"score={score:.2f} < {MATCH_HIGH_CONFIDENCE}")
            continue
        if size_ratio < MIN_BAND_SIZE_RATIO:
            print(f"  [품질필터] skip: D[{d_idx}]↔V[{v_idx}] "
                  f"size_ratio={size_ratio:.2f} < {MIN_BAND_SIZE_RATIO}")
            continue
        if cw_ratio < 0.6:
            print(f"  [품질필터] skip: D[{d_idx}]↔V[{v_idx}] "
                  f"cw_ratio={cw_ratio:.2f} (d_cw={d_cw}, v_cw={v_cw})")
            continue
        high_confidence.append((d_idx, v_idx))

    print(f"  [품질필터] {len(sorted_matches)}개 중 {len(high_confidence)}개 통과")

    # ── 1. 좌우 마진 ──
    for d_idx, v_idx in high_confidence:
        db = design_bands[d_idx]
        vb = dev_bands[v_idx]

        left_diff = abs(db["left_margin"] - vb["left_margin"])
        if left_diff >= MIN_MARGIN_DIFF:
            margin_w = max(vb["left_margin"], db["left_margin"], 10)
            differences.append({
                "type": "left_margin",
                "severity": _proportional_severity(left_diff, max(db["left_margin"], vb["left_margin"], 1)),
                "design_value": f"{db['left_margin']}px",
                "dev_value": f"{vb['left_margin']}px",
                "diff_px": left_diff,
                "band_above_idx": v_idx, "band_below_idx": v_idx,
                "bbox_x": 0, "bbox_y": vb["y_start"],
                "bbox_w": margin_w, "bbox_h": vb["height"],
                "design_bbox_x": 0, "design_bbox_y": db["y_start"],
                "design_bbox_w": margin_w, "design_bbox_h": db["height"],
            })

        right_diff = abs(db["right_margin"] - vb["right_margin"])
        if right_diff >= MIN_MARGIN_DIFF:
            margin_w = max(vb["right_margin"], db["right_margin"], 10)
            differences.append({
                "type": "right_margin",
                "severity": _proportional_severity(right_diff, max(db["right_margin"], vb["right_margin"], 1)),
                "design_value": f"{db['right_margin']}px",
                "dev_value": f"{vb['right_margin']}px",
                "diff_px": right_diff,
                "band_above_idx": v_idx, "band_below_idx": v_idx,
                "bbox_x": img_w - margin_w, "bbox_y": vb["y_start"],
                "bbox_w": margin_w, "bbox_h": vb["height"],
                "design_bbox_x": img_w - margin_w, "design_bbox_y": db["y_start"],
                "design_bbox_w": margin_w, "design_bbox_h": db["height"],
            })

    # ── 2. 밴드 높이 ──
    for d_idx, v_idx in high_confidence:
        db = design_bands[d_idx]
        vb = dev_bands[v_idx]
        height_diff = abs(db["height"] - vb["height"])

        if height_diff >= MIN_HEIGHT_DIFF:
            differences.append({
                "type": "element_height",
                "severity": _proportional_severity(height_diff, max(db["height"], vb["height"], 1)),
                "design_value": f"{db['height']}px",
                "dev_value": f"{vb['height']}px",
                "diff_px": height_diff,
                "band_above_idx": v_idx, "band_below_idx": v_idx,
                "bbox_x": vb["left_margin"], "bbox_y": vb["y_start"],
                "bbox_w": vb["content_width"], "bbox_h": vb["height"],
                "design_bbox_x": db["left_margin"], "design_bbox_y": db["y_start"],
                "design_bbox_w": db["content_width"], "design_bbox_h": db["height"],
            })

    # 심각도 → 위치 순 정렬
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    differences.sort(key=lambda d: (sev_order.get(d["severity"], 2), d["bbox_y"]))

    return differences


# ═══════════════════════════════════════════════════════════
# 심각도 판정 (v2: 비례적)
# ═══════════════════════════════════════════════════════════

def _proportional_severity(diff_px: int, reference_px: int) -> str:
    """
    절대 차이 + 상대 비율을 결합하여 심각도 판정.
    예: 6px 차이라도 10px 요소에서는 critical, 200px 요소에서는 minor.
    """
    ratio = diff_px / max(reference_px, 1)

    # 절대 기준: 큰 차이는 항상 심각
    if diff_px >= 15:
        return "critical"
    if diff_px >= 8:
        # 비율도 고려
        if ratio > 0.3:
            return "critical"
        return "major"

    # 작은 절대 차이: 비율이 높으면 심각
    if ratio > 0.5:
        return "critical"
    if ratio > 0.25:
        return "major"
    return "minor"


# ═══════════════════════════════════════════════════════════
# 겹치는 차이 병합
# ═══════════════════════════════════════════════════════════

def _merge_overlapping(differences: List[Dict]) -> List[Dict]:
    """수직으로 겹치거나 가까운 동일 타입 차이를 병합."""
    if len(differences) <= 1:
        return differences

    # 타입 + y위치로 정렬
    sorted_diffs = sorted(differences, key=lambda d: (d["type"], d["bbox_y"]))

    merged = [sorted_diffs[0]]
    for diff in sorted_diffs[1:]:
        last = merged[-1]

        # 같은 타입이고 수직으로 가까운 경우 병합
        same_type = diff["type"] == last["type"]
        y_overlap = diff["bbox_y"] < last["bbox_y"] + last["bbox_h"] + MERGE_DISTANCE_Y

        if same_type and y_overlap:
            # 더 큰 diff_px를 가진 것 유지, bbox 확장
            if diff["diff_px"] > last["diff_px"]:
                merged[-1] = diff
            # bbox를 합치는 대신, 더 심각한 것을 유지
            continue
        else:
            merged.append(diff)

    # 다시 심각도 → 위치 순 정렬
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    merged.sort(key=lambda d: (sev_order.get(d["severity"], 2), d["bbox_y"]))

    return merged


# ═══════════════════════════════════════════════════════════
# v6: 요소 단위(Element-Level) 감지 + 매칭 + 비교
# ═══════════════════════════════════════════════════════════

def _detect_ui_elements(
    img: np.ndarray,
    exclude_top: int = 0,
    min_area: int = 80,
) -> List[Dict]:
    """
    UI 요소를 개별 행(row) 단위로 감지.

    v10: 세밀한 요소 감지
    - 수직 dilation을 최소화 (2px) → 개별 텍스트 줄, 토글 행, 버튼을 각각 감지
    - 수평 dilation은 유지 → 같은 줄의 텍스트+아이콘+토글을 하나의 행으로 연결
    - 이렇게 하면 행 사이의 간격(12px, 16px, 20px 등)을 정밀 측정 가능

    이전(v8) 문제: kh=8px → 12~20px 간격의 요소가 전부 하나로 합쳐짐
    → "일러스트+타이틀+설명+토글"이 하나의 거대 blob → 간격 측정 불가
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    content = _compute_adaptive_content(gray)

    # 상태바 제외
    if exclude_top > 0:
        content[:exclude_top, :] = False

    content_u8 = content.astype(np.uint8) * 255

    # ── 팽창으로 인접 콘텐츠 연결 (행 그룹핑) ──
    # 수평: 같은 줄의 텍스트+아이콘+토글을 하나의 행으로 연결
    kw = max(15, w // 10)  # 넓게 연결 (같은 행의 요소)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 1))
    # 수직: 최소화 — 글자의 ascender/descender만 연결, 행 간 간격은 보존
    kh = max(2, h // 400)  # v10: 2px (이전 8px → 개별 행 분리)
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kh))

    dilated = cv2.dilate(content_u8, kernel_h, iterations=1)
    dilated = cv2.dilate(dilated, kernel_v, iterations=1)

    # ── 연결 컴포넌트 분석 ──
    num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(dilated)

    elements: List[Dict] = []
    for i in range(1, num_labels):  # 0 = 배경
        x, y, el_w, el_h, area = stats[i]
        if area < min_area or el_w < 4 or el_h < 4:
            continue

        # v8: 요소 영역의 시각적 지문(fingerprint) 계산
        region = img[y:y+el_h, x:x+el_w]
        hist = cv2.calcHist([region], [0, 1, 2], None, [8, 8, 8],
                            [0, 256, 0, 256, 0, 256])
        cv2.normalize(hist, hist)

        elements.append({
            "x": int(x),
            "y": int(y),
            "w": int(el_w),
            "h": int(el_h),
            "y_end": int(y + el_h),
            "center_x": float(centroids[i][0]),
            "center_y": float(centroids[i][1]),
            "_hist": hist.flatten(),  # 매칭용 내부 필드
        })

    # y좌표 → x좌표 순 정렬
    elements.sort(key=lambda e: (e["y"], e["x"]))

    print(f"  [요소감지] {len(elements)}개 UI 요소 감지 "
          f"(exclude_top={exclude_top}, kw={kw}, kh={kh})")
    for i, e in enumerate(elements):
        print(f"    E[{i}] x={e['x']} y={e['y']} "
              f"w={e['w']}×h={e['h']} center=({e['center_x']:.0f},{e['center_y']:.0f})")

    return elements


def _match_elements(
    design_elems: List[Dict],
    dev_elems: List[Dict],
    img_w: int,
    img_h: int,
    design_img: Optional[np.ndarray] = None,
    dev_img: Optional[np.ndarray] = None,
) -> List[Tuple[int, int, float]]:
    """
    v8: 순서 보존 DP + 시각적 유사도 + SSIM 크롭 검증.

    이전(v6) 문제점:
    - 그리디: 순서가 꼬여서 상단 요소가 하단과 매칭되는 경우 발생
    - 위치+크기만: 다른 요소를 같은 요소로 매칭 (시각적 확인 없음)

    v8 개선:
    1. 히스토그램 시각적 유사도 30% 추가 (위치 35% + 크기 15% + 시각 30% + 수평정렬 20%)
    2. 순서 보존 DP (위→아래 순서 보장)
    3. 매칭 후 SSIM 크롭 검증 (0.3 미만이면 거부 — 다른 요소)
    """
    if not design_elems or not dev_elems:
        return []

    n_d = len(design_elems)
    n_v = len(dev_elems)

    # ── 유사도 매트릭스 계산 ──
    score_matrix = np.zeros((n_d, n_v))
    for di in range(n_d):
        de = design_elems[di]
        for vi in range(n_v):
            ve = dev_elems[vi]

            # 1. Y위치 유사도 (수직 위치가 핵심)
            dy = abs(de["center_y"] / img_h - ve["center_y"] / img_h)
            y_sim = max(0.0, 1.0 - dy * 5)

            # 2. X위치 유사도 (수평 정렬)
            dx = abs(de["center_x"] / img_w - ve["center_x"] / img_w)
            x_sim = max(0.0, 1.0 - dx * 4)

            # 3. 크기 유사도
            w_ratio = min(de["w"], ve["w"]) / max(de["w"], ve["w"], 1)
            h_ratio = min(de["h"], ve["h"]) / max(de["h"], ve["h"], 1)
            size_sim = (w_ratio + h_ratio) / 2

            # 4. 시각적 유사도 (히스토그램 상관)
            visual_sim = 0.0
            d_hist = de.get("_hist")
            v_hist = ve.get("_hist")
            if d_hist is not None and v_hist is not None:
                visual_sim = cv2.compareHist(
                    d_hist.astype(np.float32),
                    v_hist.astype(np.float32),
                    cv2.HISTCMP_CORREL,
                )
                visual_sim = max(0.0, visual_sim)

            # 결합: Y위치 35% + 시각 30% + 수평정렬 20% + 크기 15%
            score_matrix[di, vi] = (
                y_sim * 0.35 + visual_sim * 0.30 +
                x_sim * 0.20 + size_sim * 0.15
            )

    # ── 순서 보존 DP 매칭 (밴드 매칭과 동일한 접근) ──
    MIN_ELEM_SCORE = 0.40  # v6 0.35 → v8 0.40 (더 보수적)
    dp = np.zeros((n_d + 1, n_v + 1))
    choice = [[None] * (n_v + 1) for _ in range(n_d + 1)]

    for di in range(1, n_d + 1):
        for vi in range(1, n_v + 1):
            skip_d = dp[di - 1][vi]
            skip_v = dp[di][vi - 1]
            match_s = dp[di - 1][vi - 1] + score_matrix[di - 1][vi - 1]

            best = max(skip_d, skip_v, match_s)
            dp[di][vi] = best

            if best == match_s and score_matrix[di - 1][vi - 1] >= MIN_ELEM_SCORE:
                choice[di][vi] = "match"
            elif best == skip_d:
                choice[di][vi] = "skip_d"
            else:
                choice[di][vi] = "skip_v"

    # 역추적
    raw_matches = []
    di, vi = n_d, n_v
    while di > 0 and vi > 0:
        if choice[di][vi] == "match":
            raw_matches.append((di - 1, vi - 1))
            di -= 1
            vi -= 1
        elif choice[di][vi] == "skip_d":
            di -= 1
        else:
            vi -= 1
    raw_matches.reverse()

    # ── SSIM 크롭 검증 — 매칭된 요소가 실제로 같은 것인지 확인 ──
    matches: List[Tuple[int, int, float]] = []
    for d_idx, v_idx in raw_matches:
        s = float(score_matrix[d_idx][v_idx])
        de = design_elems[d_idx]
        ve = dev_elems[v_idx]

        verified = True
        if design_img is not None and dev_img is not None:
            # 두 요소를 동일 크기로 크롭하여 SSIM 비교
            d_crop = design_img[de["y"]:de["y_end"], de["x"]:de["x"]+de["w"]]
            v_crop = dev_img[ve["y"]:ve["y_end"], ve["x"]:ve["x"]+ve["w"]]
            if d_crop.size > 0 and v_crop.size > 0:
                # 작은 쪽 크기로 리사이즈
                target_h = min(d_crop.shape[0], v_crop.shape[0], 120)
                target_w = min(d_crop.shape[1], v_crop.shape[1], 120)
                if target_h >= 7 and target_w >= 7:
                    d_resized = cv2.resize(d_crop, (target_w, target_h))
                    v_resized = cv2.resize(v_crop, (target_w, target_h))
                    d_g = cv2.cvtColor(d_resized, cv2.COLOR_BGR2GRAY)
                    v_g = cv2.cvtColor(v_resized, cv2.COLOR_BGR2GRAY)
                    crop_ssim = ssim(d_g, v_g)
                    if crop_ssim < 0.15:
                        print(f"  [SSIM거부] D[{d_idx}]↔V[{v_idx}] "
                              f"ssim={crop_ssim:.2f} < 0.15 — 다른 요소")
                        verified = False

        if verified:
            matches.append((d_idx, v_idx, s))

    print(f"  [요소매칭v8] DP {len(raw_matches)}개 → SSIM검증 후 {len(matches)}개 "
          f"(design={n_d}, dev={n_v})")
    for d_i, v_i, sc in matches:
        de = design_elems[d_i]
        ve = dev_elems[v_i]
        print(f"    D[{d_i}](y={de['y']}) ↔ V[{v_i}](y={ve['y']}) "
              f"score={sc:.2f}")

    return matches


def _find_containing_band_idx(elem: Dict, bands: List[Dict]) -> int:
    """요소가 속하는 밴드의 인덱스를 찾는다. 없으면 가장 가까운 밴드."""
    best_idx = 0
    best_dist = float("inf")
    cy = elem["center_y"]

    for i, b in enumerate(bands):
        if b["y_start"] <= cy <= b["y_end"]:
            return i
        dist = min(abs(cy - b["y_start"]), abs(cy - b["y_end"]))
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    return best_idx


def _compare_element_diffs(
    matches: List[Tuple[int, int, float]],
    design_elems: List[Dict],
    dev_elems: List[Dict],
    dev_bands: List[Dict],
    img_w: int,
    img_h: int,
) -> List[Dict]:
    """
    매칭된 요소 쌍의 구조적 차이를 측정.

    비교 항목:
    1. 연속 요소 쌍 간의 수직 간격 (gap between elements)
    2. 요소 높이 (element height)
    3. 요소 수평 위치 (left margin / horizontal position)
    4. 요소 너비 (element width)

    핵심: 밴드가 아닌 개별 요소 단위이므로, 복잡한 UI에서도
    각 요소의 위치/크기 차이를 정확히 측정할 수 있다.
    """
    diffs: List[Dict] = []

    # v8 품질 필터: 신뢰도 + 구조적 유사성 + 크기 비율
    confident: List[Tuple[int, int, float]] = []
    for di, vi, s in matches:
        de = design_elems[di]
        ve = dev_elems[vi]

        if s < MATCH_HIGH_CONFIDENCE:
            print(f"  [요소필터] skip: D[{di}]↔V[{vi}] score={s:.2f}")
            continue

        # 너비 비율: 너무 다르면 다른 요소
        w_ratio = min(de["w"], ve["w"]) / max(de["w"], ve["w"], 1)
        if w_ratio < 0.5:
            print(f"  [요소필터] skip: D[{di}]↔V[{vi}] w_ratio={w_ratio:.2f}")
            continue

        # v8: 높이 비율도 확인 — 높이가 3배 이상 다르면 다른 요소
        h_ratio = min(de["h"], ve["h"]) / max(de["h"], ve["h"], 1)
        if h_ratio < 0.33:
            print(f"  [요소필터] skip: D[{di}]↔V[{vi}] h_ratio={h_ratio:.2f}")
            continue

        # v8: Y위치가 너무 멀면 다른 요소 (화면의 20% 이상 떨어짐)
        y_dist = abs(de["center_y"] - ve["center_y"]) / img_h
        if y_dist > 0.20:
            print(f"  [요소필터] skip: D[{di}]↔V[{vi}] y_dist={y_dist:.2f}")
            continue

        confident.append((di, vi, s))

    print(f"  [요소비교v8] {len(matches)}개 중 {len(confident)}개 고신뢰도 매칭")

    # ── 1. 연속 요소 쌍 간 수직 간격 ──
    # 매칭을 디자인 y 순으로 정렬
    by_y = sorted(confident, key=lambda m: design_elems[m[0]]["y"])

    for i in range(len(by_y) - 1):
        d_idx_a, v_idx_a, _sa = by_y[i]
        d_idx_b, v_idx_b, _sb = by_y[i + 1]

        de_a = design_elems[d_idx_a]
        de_b = design_elems[d_idx_b]
        ve_a = dev_elems[v_idx_a]
        ve_b = dev_elems[v_idx_b]

        # 같은 행에 있거나 겹치는 요소는 수직 간격 비교 안 함
        if de_a["y_end"] > de_b["y"]:
            continue

        d_gap = de_b["y"] - de_a["y_end"]
        v_gap = ve_b["y"] - ve_a["y_end"]

        # 음수 갭 = 요소가 겹침 (구조적으로 다른 영역) → skip
        if d_gap < 0 or v_gap < 0:
            continue

        gap_diff = abs(d_gap - v_gap)

        if gap_diff < MIN_SPACING_DIFF:
            continue

        # v8: 갭 비율 안전장치 — 한쪽이 0이고 다른 쪽이 큰 경우 = 매칭 오류 가능성
        max_gap = max(d_gap, v_gap)
        min_gap = min(d_gap, v_gap)
        if max_gap > 0 and min_gap == 0 and max_gap > img_h * 0.05:
            continue
        # 갭 비율이 5배 이상 차이나면 = 다른 영역 비교 중
        if min_gap > 0 and max_gap / min_gap > 5:
            continue

        # 갭 위치로 타입 결정
        gap_center_y = (ve_a["y_end"] + ve_b["y"]) / 2
        if gap_center_y < img_h * 0.1:
            gap_type = "top_margin"
        elif gap_center_y > img_h * 0.92:
            gap_type = "bottom_margin"
        else:
            gap_type = "vertical_spacing"

        above_band = _find_containing_band_idx(ve_a, dev_bands)
        below_band = _find_containing_band_idx(ve_b, dev_bands)

        diffs.append({
            "type": gap_type,
            "severity": _proportional_severity(gap_diff, max(d_gap, v_gap, 1)),
            "design_value": f"{d_gap}px",
            "dev_value": f"{v_gap}px",
            "diff_px": gap_diff,
            "band_above_idx": above_band,
            "band_below_idx": below_band,
            "bbox_x": 0,
            "bbox_y": ve_a["y_end"],
            "bbox_w": img_w,
            "bbox_h": max(v_gap, 1),
            "design_bbox_x": 0,
            "design_bbox_y": de_a["y_end"],
            "design_bbox_w": img_w,
            "design_bbox_h": max(d_gap, 1),
        })

    # ── 2. 요소 높이 ──
    for d_idx, v_idx, _s in confident:
        de = design_elems[d_idx]
        ve = dev_elems[v_idx]
        h_diff = abs(de["h"] - ve["h"])

        if h_diff < MIN_HEIGHT_DIFF:
            continue

        band_idx = _find_containing_band_idx(ve, dev_bands)
        diffs.append({
            "type": "element_height",
            "severity": _proportional_severity(h_diff, max(de["h"], ve["h"], 1)),
            "design_value": f"{de['h']}px",
            "dev_value": f"{ve['h']}px",
            "diff_px": h_diff,
            "band_above_idx": band_idx,
            "band_below_idx": band_idx,
            "bbox_x": ve["x"], "bbox_y": ve["y"],
            "bbox_w": ve["w"], "bbox_h": ve["h"],
            "design_bbox_x": de["x"], "design_bbox_y": de["y"],
            "design_bbox_w": de["w"], "design_bbox_h": de["h"],
        })

    # ── 3. 수평 위치 (좌측 마진) ──
    for d_idx, v_idx, _s in confident:
        de = design_elems[d_idx]
        ve = dev_elems[v_idx]
        x_diff = abs(de["x"] - ve["x"])

        if x_diff < MIN_MARGIN_DIFF:
            continue

        # v8: 마진 비율 안전장치 — 한쪽이 0이고 다른쪽이 큰 경우 = 다른 요소
        max_x = max(de["x"], ve["x"])
        min_x = min(de["x"], ve["x"])
        if min_x == 0 and max_x > img_w * 0.15:
            continue
        # 마진이 5배 이상 차이나면 = 다른 요소 비교 중
        if min_x > 0 and max_x / min_x > 5:
            continue

        band_idx = _find_containing_band_idx(ve, dev_bands)
        margin_w = max(de["x"], ve["x"], 10)
        diffs.append({
            "type": "left_margin",
            "severity": _proportional_severity(x_diff, max(de["x"], ve["x"], 1)),
            "design_value": f"{de['x']}px",
            "dev_value": f"{ve['x']}px",
            "diff_px": x_diff,
            "band_above_idx": band_idx,
            "band_below_idx": band_idx,
            "bbox_x": 0, "bbox_y": ve["y"],
            "bbox_w": margin_w, "bbox_h": ve["h"],
            "design_bbox_x": 0, "design_bbox_y": de["y"],
            "design_bbox_w": margin_w, "design_bbox_h": de["h"],
        })

    # ── 4. 요소 너비 ──
    for d_idx, v_idx, _s in confident:
        de = design_elems[d_idx]
        ve = dev_elems[v_idx]
        w_diff = abs(de["w"] - ve["w"])

        if w_diff < MIN_MARGIN_DIFF:
            continue

        # 너비 비율이 비슷하면 skip (콘텐츠 길이 차이일 수 있음)
        w_ratio = min(de["w"], ve["w"]) / max(de["w"], ve["w"], 1)
        if w_ratio > 0.85:
            continue

        band_idx = _find_containing_band_idx(ve, dev_bands)
        diffs.append({
            "type": "element_width",
            "severity": _proportional_severity(w_diff, max(de["w"], ve["w"], 1)),
            "design_value": f"{de['w']}px",
            "dev_value": f"{ve['w']}px",
            "diff_px": w_diff,
            "band_above_idx": band_idx,
            "band_below_idx": band_idx,
            "bbox_x": ve["x"], "bbox_y": ve["y"],
            "bbox_w": ve["w"], "bbox_h": ve["h"],
            "design_bbox_x": de["x"], "design_bbox_y": de["y"],
            "design_bbox_w": de["w"], "design_bbox_h": de["h"],
        })

    # 심각도 → 위치 순 정렬
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    diffs.sort(key=lambda d: (sev_order.get(d["severity"], 2), d["bbox_y"]))

    return diffs


# ═══════════════════════════════════════════════════════════
# 밴드 라벨링용 유틸리티
# ═══════════════════════════════════════════════════════════

def heuristic_label(band: Dict, idx: int, total: int, img_w: int, img_h: int) -> str:
    """밴드의 특성으로 UI 요소 타입을 휴리스틱 추정."""
    rel_y = band["center_y"] / img_h
    width_ratio = band["content_width"] / img_w
    height = band["height"]

    if idx == 0 and rel_y < 0.06 and height < img_h * 0.06:
        return "상태바"
    if rel_y < 0.12 and height < img_h * 0.08:
        return "헤더"
    if height > img_h * 0.15 and band["density"] > 0.3:
        return "이미지/일러스트"
    if rel_y > 0.75 and width_ratio > 0.6 and height < img_h * 0.1:
        return "CTA 버튼"
    if idx == total - 1 and rel_y > 0.9:
        return "하단 내비게이션"
    if height < img_h * 0.05:
        return "텍스트"
    if height < img_h * 0.12:
        return "콘텐츠"
    return "섹션"


def format_differences_with_labels(
    differences: List[Dict],
    design_bands: List[Dict],
    dev_bands: List[Dict],
    labels: Optional[List[str]],
    img_w: int,
    img_h: int,
) -> List[Dict]:
    """CV 측정 결과 + 라벨을 결합하여 최종 QA 리포트 형식으로 변환."""
    total = len(dev_bands)

    if not labels or len(labels) < total:
        labels = [
            heuristic_label(b, i, total, img_w, img_h)
            for i, b in enumerate(dev_bands)
        ]

    formatted = []
    for diff in differences:
        dtype = diff["type"]
        above_idx = diff.get("band_above_idx", -1)
        below_idx = diff.get("band_below_idx", -1)

        # 디자인 기준 차이 방향
        d_val = int(diff['design_value'].replace('px', ''))
        v_val = int(diff['dev_value'].replace('px', ''))
        delta = v_val - d_val
        direction = f"{abs(delta)}px {'초과' if delta > 0 else '부족'}"

        if dtype == "vertical_spacing":
            above_label = labels[above_idx] if 0 <= above_idx < len(labels) else "상단"
            below_label = labels[below_idx] if 0 <= below_idx < len(labels) else "하단"
            description = (
                f"{above_label}↔{below_label} 수직 간격 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "spacing"

        elif dtype == "top_margin":
            below_label = labels[below_idx] if 0 <= below_idx < len(labels) else "첫 번째 요소"
            description = (
                f"화면 상단~{below_label} 여백 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "spacing"

        elif dtype == "bottom_margin":
            above_label = labels[above_idx] if 0 <= above_idx < len(labels) else "마지막 요소"
            description = (
                f"{above_label} 하단 여백 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "spacing"

        elif dtype == "left_margin":
            band_label = labels[above_idx] if 0 <= above_idx < len(labels) else "요소"
            description = (
                f"{band_label} 좌측 여백 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "spacing"

        elif dtype == "right_margin":
            band_label = labels[above_idx] if 0 <= above_idx < len(labels) else "요소"
            description = (
                f"{band_label} 우측 여백 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "spacing"

        elif dtype == "element_height":
            band_label = labels[above_idx] if 0 <= above_idx < len(labels) else "요소"
            description = (
                f"{band_label} 높이 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "layout"

        elif dtype == "element_width":
            band_label = labels[above_idx] if 0 <= above_idx < len(labels) else "요소"
            description = (
                f"{band_label} 너비 — "
                f"디자인 기준 {diff['design_value']}, 개발 {diff['dev_value']} ({direction})"
            )
            category = "layout"

        else:
            description = f"차이 감지 — 디자인 기준 {diff['design_value']} → 개발 {diff['dev_value']}"
            category = "layout"

        formatted.append({
            "category": category,
            "severity": diff["severity"],
            "description": description,
            "design_value": diff["design_value"],
            "dev_value": diff["dev_value"],
            "bbox_x": diff["bbox_x"],
            "bbox_y": diff["bbox_y"],
            "bbox_w": diff["bbox_w"],
            "bbox_h": diff["bbox_h"],
            "design_bbox_x": diff.get("design_bbox_x", diff["bbox_x"]),
            "design_bbox_y": diff.get("design_bbox_y", diff["bbox_y"]),
            "design_bbox_w": diff.get("design_bbox_w", diff["bbox_w"]),
            "design_bbox_h": diff.get("design_bbox_h", diff["bbox_h"]),
        })

    return formatted


# ═══════════════════════════════════════════════════════════
# v7: 픽셀 diff 영역 CV 정밀 분석
# ═══════════════════════════════════════════════════════════

def analyze_pixel_regions(
    design_path: str,
    dev_path: str,
    pixel_regions: List[Dict],
    dev_w: int,
    dev_h: int,
) -> List[Dict]:
    """
    pixel diff 영역(ground truth)을 CV로 정밀 분석하여 구체적 측정값 생성.

    AI 없이 동작하는 핵심 엔진:
    - 각 pixel region에서 디자인/개발 이미지를 크롭
    - 크롭 내부의 콘텐츠를 분석하여 변화 유형을 분류
    - 정확한 px 측정값이 포함된 diff 생성

    분류 유형:
    1. missing_element: 디자인에만 콘텐츠 존재 (개발에서 누락)
    2. added_element: 개발에만 콘텐츠 존재 (추가됨)
    3. color_change: 같은 위치, 다른 색상
    4. position_shift: 콘텐츠가 이동됨 (수직/수평 오프셋)
    5. size_change: 콘텐츠 크기 변경
    6. visual_change: 기타 시각적 변경
    """
    design = cv2.imread(design_path)
    dev = cv2.imread(dev_path)
    if design is None or dev is None:
        return []

    # 정규화: dev 크기에 맞춤
    if design.shape[1] != dev.shape[1]:
        scale = dev.shape[1] / design.shape[1]
        new_h = int(design.shape[0] * scale)
        design = cv2.resize(design, (dev.shape[1], new_h), interpolation=cv2.INTER_LANCZOS4)

    compare_h = min(design.shape[0], dev.shape[0])
    design = design[:compare_h]
    dev_img = dev[:compare_h]

    img_h, img_w = dev_img.shape[:2]
    total_area = img_w * img_h

    # pixel_regions 좌표는 이미 원본 dev 공간 → 정규화 공간으로 역변환 필요
    scale_x = img_w / dev_w if dev_w > 0 else 1.0
    scale_y = img_h / dev_h if dev_h > 0 else 1.0

    diffs: List[Dict] = []

    for idx, region in enumerate(pixel_regions):
        # 좌표 변환 (원본 → 정규화 공간)
        rx = int(region["x"] * scale_x)
        ry = int(region["y"] * scale_y)
        rw = int(region["w"] * scale_x)
        rh = int(region["h"] * scale_y)

        # 경계 클리핑
        rx = max(0, min(rx, img_w - 1))
        ry = max(0, min(ry, img_h - 1))
        rw = max(1, min(rw, img_w - rx))
        rh = max(1, min(rh, img_h - ry))

        if rw < 4 or rh < 4:
            continue

        # 크롭
        d_crop = design[ry:ry+rh, rx:rx+rw]
        v_crop = dev_img[ry:ry+rh, rx:rx+rw]

        if d_crop.size == 0 or v_crop.size == 0:
            continue

        # 분석
        result = _analyze_single_region(
            d_crop, v_crop, rx, ry, rw, rh, img_w, img_h, idx,
            region.get("sensitivity", "structural"),
        )
        if result:
            # bbox를 원본 dev 공간으로 변환
            result["bbox_x"] = region["x"]
            result["bbox_y"] = region["y"]
            result["bbox_w"] = region["w"]
            result["bbox_h"] = region["h"]
            # design bbox도 동일 영역 (정규화됨)
            result["design_bbox_x"] = region["x"]
            result["design_bbox_y"] = region["y"]
            result["design_bbox_w"] = region["w"]
            result["design_bbox_h"] = region["h"]
            diffs.append(result)

    print(f"[PixelCV] {len(pixel_regions)}개 영역 → {len(diffs)}개 정밀 diff 생성")
    return diffs


def _analyze_single_region(
    d_crop: np.ndarray,
    v_crop: np.ndarray,
    rx: int, ry: int, rw: int, rh: int,
    img_w: int, img_h: int,
    idx: int,
    sensitivity: str,
) -> Optional[Dict]:
    """단일 pixel diff 영역을 CV로 분석하여 변화 유형과 측정값을 판정."""
    area = rw * rh
    total_area = img_w * img_h
    area_ratio = area / total_area if total_area > 0 else 0

    # 위치 기반 라벨
    rel_y = (ry + rh / 2) / img_h
    if rel_y < 0.08:
        location = "상태바/헤더"
    elif rel_y < 0.20:
        location = "상단"
    elif rel_y < 0.75:
        location = "본문"
    elif rel_y < 0.90:
        location = "하단"
    else:
        location = "내비게이션"

    # ── 1. 콘텐츠 밀도 비교 (missing/added 판정) ──
    d_gray = cv2.cvtColor(d_crop, cv2.COLOR_BGR2GRAY)
    v_gray = cv2.cvtColor(v_crop, cv2.COLOR_BGR2GRAY)

    # 작은 크롭에서는 medianBlur 대신 간단한 임계값 사용
    min_dim = min(rw, rh)
    if min_dim < 100:
        # 단순 차이 기반: 전체 크롭 평균에서 벗어난 픽셀 = 콘텐츠
        d_mean_val = float(np.mean(d_gray))
        v_mean_val = float(np.mean(v_gray))
        d_content = np.abs(d_gray.astype(np.float32) - d_mean_val) > 20
        v_content = np.abs(v_gray.astype(np.float32) - v_mean_val) > 20
    else:
        d_content = _compute_adaptive_content(d_gray, bg_diff_thresh=15)
        v_content = _compute_adaptive_content(v_gray, bg_diff_thresh=15)

    d_density = float(np.mean(d_content))
    v_density = float(np.mean(v_content))

    # 콘텐츠 유무 차이 판정 (한쪽만 콘텐츠가 있을 때)
    DENSITY_THRESH = 0.05
    if d_density > DENSITY_THRESH and v_density < DENSITY_THRESH * 0.5:
        # 디자인에만 콘텐츠 → 개발에서 누락
        severity = "critical" if area_ratio > 0.01 else "major"
        return {
            "category": "content",
            "severity": severity,
            "description": f"{location} 영역 요소 누락 — 디자인에 있는 요소가 개발에서 빠짐",
            "design_value": "콘텐츠 있음",
            "dev_value": "비어 있음",
        }

    if v_density > DENSITY_THRESH and d_density < DENSITY_THRESH * 0.5:
        # 개발에만 콘텐츠 → 추가된 요소
        severity = "major" if area_ratio > 0.01 else "minor"
        return {
            "category": "content",
            "severity": severity,
            "description": f"{location} 영역 요소 추가 — 디자인에 없는 요소가 개발에 추가됨",
            "design_value": "비어 있음",
            "dev_value": "콘텐츠 있음",
        }

    # ── 2. 색상 차이 분석 ──
    d_mean = np.mean(d_crop.astype(np.float32), axis=(0, 1))  # [B, G, R]
    v_mean = np.mean(v_crop.astype(np.float32), axis=(0, 1))
    color_diff = float(np.linalg.norm(d_mean - v_mean))

    # 색상이 크게 다른 경우 (배경색 변경 등)
    if color_diff > 40:
        d_hex = "#{:02x}{:02x}{:02x}".format(int(d_mean[2]), int(d_mean[1]), int(d_mean[0]))
        v_hex = "#{:02x}{:02x}{:02x}".format(int(v_mean[2]), int(v_mean[1]), int(v_mean[0]))
        severity = "major" if color_diff > 80 else "minor"
        return {
            "category": "visual",
            "severity": severity,
            "description": f"{location} 영역 색상 변경 — 배경 또는 요소 색상이 다름",
            "design_value": d_hex,
            "dev_value": v_hex,
        }

    # ── 3. 콘텐츠 위치 이동 분석 ──
    if d_density > DENSITY_THRESH and v_density > DENSITY_THRESH:
        # 양쪽 모두 콘텐츠 있음 → 위치/크기 차이 분석
        d_coords = np.argwhere(d_content)
        v_coords = np.argwhere(v_content)

        if len(d_coords) > 10 and len(v_coords) > 10:
            # 콘텐츠 무게중심 비교
            d_cy, d_cx = np.mean(d_coords, axis=0)
            v_cy, v_cx = np.mean(v_coords, axis=0)
            shift_x = abs(d_cx - v_cx)
            shift_y = abs(d_cy - v_cy)

            # 콘텐츠 바운딩 박스 비교
            d_y1, d_x1 = np.min(d_coords, axis=0)
            d_y2, d_x2 = np.max(d_coords, axis=0)
            v_y1, v_x1 = np.min(v_coords, axis=0)
            v_y2, v_x2 = np.max(v_coords, axis=0)

            d_content_w = d_x2 - d_x1
            d_content_h = d_y2 - d_y1
            v_content_w = v_x2 - v_x1
            v_content_h = v_y2 - v_y1

            # 크기 변화
            w_change = abs(d_content_w - v_content_w)
            h_change = abs(d_content_h - v_content_h)

            if shift_y > 3 and shift_y > shift_x:
                # 수직 이동
                shift_dir = "아래" if v_cy > d_cy else "위"
                shift_px = int(shift_y)
                severity = _proportional_severity(shift_px, rh)
                return {
                    "category": "layout",
                    "severity": severity,
                    "description": f"{location} 영역 콘텐츠 {shift_dir}로 {shift_px}px 이동",
                    "design_value": f"y={int(d_cy)}px",
                    "dev_value": f"y={int(v_cy)}px",
                }

            if shift_x > 3 and shift_x > shift_y:
                # 수평 이동
                shift_dir = "오른쪽" if v_cx > d_cx else "왼쪽"
                shift_px = int(shift_x)
                severity = _proportional_severity(shift_px, rw)
                return {
                    "category": "layout",
                    "severity": severity,
                    "description": f"{location} 영역 콘텐츠 {shift_dir}으로 {shift_px}px 이동",
                    "design_value": f"x={int(d_cx)}px",
                    "dev_value": f"x={int(v_cx)}px",
                }

            if h_change > 3:
                severity = _proportional_severity(h_change, max(d_content_h, v_content_h, 1))
                return {
                    "category": "layout",
                    "severity": severity,
                    "description": f"{location} 영역 요소 높이 변경",
                    "design_value": f"{d_content_h}px",
                    "dev_value": f"{v_content_h}px",
                }

            if w_change > 3:
                severity = _proportional_severity(w_change, max(d_content_w, v_content_w, 1))
                return {
                    "category": "layout",
                    "severity": severity,
                    "description": f"{location} 영역 요소 너비 변경",
                    "design_value": f"{d_content_w}px",
                    "dev_value": f"{v_content_w}px",
                }

    # ── 4. 기본: 시각적 차이 (텍스트/아이콘 변경 등) ──
    if area_ratio < 0.005:
        severity = "minor"
    elif area_ratio < 0.02:
        severity = "major"
    else:
        severity = "critical"

    # 텍스트 변경 가능성 판단 (좁고 낮은 영역)
    aspect = rw / max(rh, 1)
    if aspect > 2 and rh < img_h * 0.06:
        desc = f"{location} 영역 텍스트 변경 감지"
        cat = "typography"
    elif rh > rw and rw < img_w * 0.15:
        desc = f"{location} 영역 아이콘/이미지 변경 감지"
        cat = "visual"
    else:
        desc = f"{location} 영역 시각적 차이 감지"
        cat = "visual"

    return {
        "category": cat,
        "severity": severity,
        "description": desc,
        "design_value": "",
        "dev_value": "",
    }
