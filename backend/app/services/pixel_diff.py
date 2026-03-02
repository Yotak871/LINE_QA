from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim


def compute_diff(img_a: np.ndarray, img_b: np.ndarray) -> tuple[float, list[dict]]:
    """
    두 이미지의 픽셀 차이를 다단계 민감도로 분석한다.

    Google Design QA 수준의 정밀 감지:
    - Pass 1: 구조적 차이 (레이아웃, 누락 요소)  — 높은 threshold
    - Pass 2: 세부 차이 (간격, 폰트, 색상)        — 낮은 threshold
    - Pass 3: 에지 차이 (정확한 마진/패딩 감지)    — Canny edge diff

    Returns:
        similarity_score: 0~100 유사도 점수
        regions: 차이 영역 바운딩 박스 목록 [{x, y, w, h, area, sensitivity}, ...]
    """
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)
    img_h, img_w = gray_a.shape[:2]
    total_area = img_w * img_h

    score, diff = ssim(gray_a, gray_b, full=True)
    similarity = round(float(score) * 100, 2)

    diff_uint8 = (np.abs(1 - diff) * 255).astype(np.uint8)

    all_regions = []

    # ─── Pass 1: 구조적 차이 (큰 레이아웃 변경, 누락 요소) ───
    _, thresh_structural = cv2.threshold(diff_uint8, 30, 255, cv2.THRESH_BINARY)
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh_structural = cv2.morphologyEx(thresh_structural, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 7))
    connected = cv2.morphologyEx(thresh_structural, cv2.MORPH_CLOSE, kernel_close)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        all_regions.append({
            "x": int(x), "y": int(y), "w": int(w), "h": int(h),
            "area": int(area), "sensitivity": "structural",
        })

    # ─── Pass 2: 세부 차이 (간격, 색상, 타이포) ───
    _, thresh_detail = cv2.threshold(diff_uint8, 12, 255, cv2.THRESH_BINARY)
    kernel_open_s = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    thresh_detail = cv2.morphologyEx(thresh_detail, cv2.MORPH_OPEN, kernel_open_s)
    kernel_close_s = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    connected_detail = cv2.morphologyEx(thresh_detail, cv2.MORPH_CLOSE, kernel_close_s)

    contours_d, _ = cv2.findContours(connected_detail, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours_d:
        area = cv2.contourArea(cnt)
        if area < 30:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        # Pass 1에서 이미 감지된 영역과 겹치는지 확인
        r = {"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": int(area)}
        if not _covered_by(r, all_regions, coverage=0.7):
            r["sensitivity"] = "detail"
            all_regions.append(r)

    # ─── Pass 3: 에지 기반 차이 (마진/패딩/보더 정밀 감지) ───
    edges_a = cv2.Canny(gray_a, 50, 150)
    edges_b = cv2.Canny(gray_b, 50, 150)
    edge_diff = cv2.absdiff(edges_a, edges_b)

    kernel_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edge_diff = cv2.morphologyEx(edge_diff, cv2.MORPH_CLOSE, kernel_edge)

    contours_e, _ = cv2.findContours(edge_diff, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours_e:
        area = cv2.contourArea(cnt)
        if area < 20:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        r = {"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": int(area)}
        if not _covered_by(r, all_regions, coverage=0.6):
            r["sensitivity"] = "edge"
            all_regions.append(r)

    # ─── 후처리: 분할 → 병합 → 정렬 ───
    MAX_REGION_RATIO = 0.15
    final_regions = []
    for r in all_regions:
        r_area = r["w"] * r["h"]
        if r_area > total_area * MAX_REGION_RATIO:
            sub_regions = _split_large_region(thresh_detail, r, img_w, img_h)
            if len(sub_regions) > 1:
                for sr in sub_regions:
                    sr["sensitivity"] = r.get("sensitivity", "structural")
                final_regions.extend(sub_regions)
            else:
                final_regions.append(r)
        else:
            final_regions.append(r)

    final_regions = _merge_overlapping(final_regions)
    final_regions.sort(key=lambda r: r["area"], reverse=True)
    final_regions = final_regions[:20]  # 최대 20개 (기존 15 → 20)

    structural_count = sum(1 for r in final_regions if r.get("sensitivity") == "structural")
    detail_count = sum(1 for r in final_regions if r.get("sensitivity") == "detail")
    edge_count = sum(1 for r in final_regions if r.get("sensitivity") == "edge")
    print(
        f"[PixelDiff] 유사도: {similarity}%, "
        f"감지 영역: {len(all_regions)}개 → 최종: {len(final_regions)}개 "
        f"(구조:{structural_count} 세부:{detail_count} 에지:{edge_count})"
    )
    return similarity, final_regions


def _covered_by(r: dict, existing: list[dict], coverage: float = 0.7) -> bool:
    """r이 existing 영역들에 의해 일정 비율 이상 커버되는지 확인."""
    r_area = r["w"] * r["h"]
    if r_area <= 0:
        return True
    for e in existing:
        ix1 = max(r["x"], e["x"])
        iy1 = max(r["y"], e["y"])
        ix2 = min(r["x"] + r["w"], e["x"] + e["w"])
        iy2 = min(r["y"] + r["h"], e["y"] + e["h"])
        if ix2 > ix1 and iy2 > iy1:
            inter = (ix2 - ix1) * (iy2 - iy1)
            if inter / r_area >= coverage:
                return True
    return False


def _split_large_region(
    thresh: np.ndarray, region: dict, img_w: int, img_h: int
) -> list[dict]:
    """큰 차이 영역을 수평 슬라이스로 분할하여 개별 UI 요소 단위로 세분화."""
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    x2 = min(x + w, img_w)
    y2 = min(y + h, img_h)

    roi = thresh[y:y2, x:x2]
    if roi.size == 0:
        return [region]

    h_proj = np.sum(roi > 0, axis=1)
    gap_threshold = w * 0.03
    is_gap = h_proj < gap_threshold

    MIN_GAP = 5
    sub_regions = []
    start = 0
    gap_count = 0

    for row in range(len(is_gap)):
        if is_gap[row]:
            gap_count += 1
        else:
            if gap_count >= MIN_GAP and row - gap_count > start:
                seg_roi = roi[start:row - gap_count, :]
                if np.sum(seg_roi > 0) > 50:
                    sub = _tight_bbox(seg_roi, x, y + start)
                    if sub:
                        sub_regions.append(sub)
                start = row
            gap_count = 0

    if start < len(is_gap):
        seg_roi = roi[start:, :]
        if np.sum(seg_roi > 0) > 50:
            sub = _tight_bbox(seg_roi, x, y + start)
            if sub:
                sub_regions.append(sub)

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

        if len(group) == 1:
            merged.append(group[0])
        else:
            min_x = min(g["x"] for g in group)
            min_y = min(g["y"] for g in group)
            max_x = max(g["x"] + g["w"] for g in group)
            max_y = max(g["y"] + g["h"] for g in group)
            # 병합 시 가장 높은 sensitivity 유지
            sens_priority = {"structural": 0, "detail": 1, "edge": 2}
            best_sens = min(group, key=lambda g: sens_priority.get(g.get("sensitivity", "structural"), 0))
            merged.append({
                "x": min_x, "y": min_y,
                "w": max_x - min_x, "h": max_y - min_y,
                "area": sum(g["area"] for g in group),
                "sensitivity": best_sens.get("sensitivity", "structural"),
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
