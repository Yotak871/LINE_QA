from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim


def compute_diff(img_a: np.ndarray, img_b: np.ndarray) -> tuple[float, list[dict]]:
    """
    두 이미지의 픽셀 차이를 분석한다.
    큰 영역을 자동으로 세분화하여 개별 UI 요소 단위의 차이를 감지한다.

    Returns:
        similarity_score: 0~100 유사도 점수
        regions: 차이 영역 바운딩 박스 목록 [{x, y, w, h, area}, ...]
    """
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)
    img_h, img_w = gray_a.shape[:2]
    total_area = img_w * img_h

    score, diff = ssim(gray_a, gray_b, full=True)
    similarity = round(float(score) * 100, 2)

    # 차이 영역 추출 (더 낮은 threshold로 미세한 차이도 감지)
    diff_uint8 = (np.abs(1 - diff) * 255).astype(np.uint8)
    _, thresh = cv2.threshold(diff_uint8, 25, 255, cv2.THRESH_BINARY)

    # 1단계: 작은 커널로 노이즈만 제거 (세부 영역 보존)
    kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_small)

    # 2단계: 약간의 dilation으로 가까운 픽셀 연결 (같은 요소 내 차이)
    kernel_connect = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 5))
    connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_connect)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_regions = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 80:  # 노이즈 제외
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        raw_regions.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": int(area)})

    # 3단계: 큰 영역을 세분화 (화면의 15% 이상이면 분할 시도)
    MAX_REGION_RATIO = 0.15
    regions = []
    for r in raw_regions:
        r_area = r["w"] * r["h"]
        if r_area > total_area * MAX_REGION_RATIO:
            sub_regions = _split_large_region(thresh, r, img_w, img_h)
            if len(sub_regions) > 1:
                regions.extend(sub_regions)
            else:
                regions.append(r)
        else:
            regions.append(r)

    # 4단계: 겹치는 영역 병합
    regions = _merge_overlapping(regions)

    # 면적 기준 내림차순 정렬
    regions.sort(key=lambda r: r["area"], reverse=True)

    # 최대 15개로 제한
    regions = regions[:15]

    print(f"[PixelDiff] 유사도: {similarity}%, 감지 영역: {len(raw_regions)}개 → 세분화 후: {len(regions)}개")
    return similarity, regions


def _split_large_region(
    thresh: np.ndarray, region: dict, img_w: int, img_h: int
) -> list[dict]:
    """큰 차이 영역을 수평 슬라이스로 분할하여 개별 UI 요소 단위로 세분화."""
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    x2 = min(x + w, img_w)
    y2 = min(y + h, img_h)

    # 해당 영역만 크롭
    roi = thresh[y:y2, x:x2]
    if roi.size == 0:
        return [region]

    # 수평 프로젝션 (각 행의 흰 픽셀 수)
    h_proj = np.sum(roi > 0, axis=1)

    # 빈 행(차이 없는 행)을 찾아서 분할 포인트 결정
    gap_threshold = w * 0.03  # 행의 3% 미만이면 "빈 행"으로 간주
    is_gap = h_proj < gap_threshold

    # 연속된 빈 행이 5px 이상이면 분할 포인트
    MIN_GAP = 5
    sub_regions = []
    start = 0
    gap_count = 0

    for row in range(len(is_gap)):
        if is_gap[row]:
            gap_count += 1
        else:
            if gap_count >= MIN_GAP and row - gap_count > start:
                # 이전 세그먼트 저장
                seg_roi = roi[start:row - gap_count, :]
                if np.sum(seg_roi > 0) > 50:
                    sub = _tight_bbox(seg_roi, x, y + start)
                    if sub:
                        sub_regions.append(sub)
                start = row
            gap_count = 0

    # 마지막 세그먼트
    if start < len(is_gap):
        seg_roi = roi[start:, :]
        if np.sum(seg_roi > 0) > 50:
            sub = _tight_bbox(seg_roi, x, y + start)
            if sub:
                sub_regions.append(sub)

    # 분할 결과가 1개 이하면 수직 분할도 시도
    if len(sub_regions) <= 1:
        sub_regions = _split_vertical(roi, x, y)

    return sub_regions if len(sub_regions) > 1 else [region]


def _split_vertical(roi: np.ndarray, offset_x: int, offset_y: int) -> list[dict]:
    """수직 방향으로 분할 시도."""
    v_proj = np.sum(roi > 0, axis=0)
    h_roi = roi.shape[0]
    gap_threshold = h_roi * 0.03
    is_gap = v_proj < gap_threshold

    MIN_GAP = 8
    sub_regions = []
    start = 0
    gap_count = 0

    for col in range(len(is_gap)):
        if is_gap[col]:
            gap_count += 1
        else:
            if gap_count >= MIN_GAP and col - gap_count > start:
                seg_roi = roi[:, start:col - gap_count]
                if np.sum(seg_roi > 0) > 50:
                    sub = _tight_bbox(seg_roi, offset_x + start, offset_y)
                    if sub:
                        sub_regions.append(sub)
                start = col
            gap_count = 0

    if start < len(is_gap):
        seg_roi = roi[:, start:]
        if np.sum(seg_roi > 0) > 50:
            sub = _tight_bbox(seg_roi, offset_x + start, offset_y)
            if sub:
                sub_regions.append(sub)

    return sub_regions


def _tight_bbox(roi: np.ndarray, offset_x: int, offset_y: int) -> Optional[dict]:
    """ROI 내에서 실제 차이 픽셀을 감싸는 타이트한 bbox를 계산."""
    coords = cv2.findNonZero(roi)
    if coords is None:
        return None
    bx, by, bw, bh = cv2.boundingRect(coords)
    # 약간의 패딩 추가
    pad = 4
    bx = max(0, bx - pad)
    by = max(0, by - pad)
    bw = min(roi.shape[1] - bx, bw + pad * 2)
    bh = min(roi.shape[0] - by, bh + pad * 2)
    area = int(np.sum(roi[by:by+bh, bx:bx+bw] > 0))
    return {
        "x": offset_x + bx,
        "y": offset_y + by,
        "w": bw,
        "h": bh,
        "area": max(area, bw * bh // 4),
    }


def _merge_overlapping(regions: list[dict], iou_threshold: float = 0.3) -> list[dict]:
    """IoU 기준으로 겹치는 영역을 병합."""
    if not regions:
        return regions

    merged = []
    used = set()

    for i, a in enumerate(regions):
        if i in used:
            continue
        group = [a]
        for j, b in enumerate(regions):
            if j <= i or j in used:
                continue
            if _iou(a, b) > iou_threshold:
                group.append(b)
                used.add(j)

        # 그룹 내 모든 영역을 하나로 병합
        if len(group) == 1:
            merged.append(group[0])
        else:
            min_x = min(g["x"] for g in group)
            min_y = min(g["y"] for g in group)
            max_x = max(g["x"] + g["w"] for g in group)
            max_y = max(g["y"] + g["h"] for g in group)
            merged.append({
                "x": min_x, "y": min_y,
                "w": max_x - min_x, "h": max_y - min_y,
                "area": sum(g["area"] for g in group),
            })
        used.add(i)

    return merged


def _iou(a: dict, b: dict) -> float:
    """두 bbox의 IoU (Intersection over Union) 계산."""
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def crop_region(img: np.ndarray, region: dict, padding: int = 10) -> np.ndarray:
    """바운딩 박스 영역을 패딩 포함 크롭."""
    h, w = img.shape[:2]
    x1 = max(0, region["x"] - padding)
    y1 = max(0, region["y"] - padding)
    x2 = min(w, region["x"] + region["w"] + padding)
    y2 = min(h, region["y"] + region["h"] + padding)
    return img[y1:y2, x1:x2]
