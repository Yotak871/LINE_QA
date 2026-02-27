from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np


def load_and_normalize(path_a: str, path_b: str) -> tuple:
    """두 이미지를 같은 크기로 정규화하여 numpy 배열로 반환.

    Returns:
        (img_a, img_b, orig_a_size, orig_b_size)
        orig_*_size = (width, height)
    """
    img_a = Image.open(path_a).convert("RGB")
    img_b = Image.open(path_b).convert("RGB")

    orig_a_size = (img_a.width, img_a.height)
    orig_b_size = (img_b.width, img_b.height)

    # 작은 쪽 기준으로 리사이즈 (비율 유지)
    target_w = min(img_a.width, img_b.width)
    target_h = min(img_a.height, img_b.height)

    img_a = img_a.resize((target_w, target_h), Image.LANCZOS)
    img_b = img_b.resize((target_w, target_h), Image.LANCZOS)

    return np.array(img_a), np.array(img_b), orig_a_size, orig_b_size


def get_image_dimensions(path: str) -> tuple:
    """이미지의 원본 (width, height) 반환."""
    img = Image.open(path)
    return img.width, img.height


def scale_regions_to_original(
    regions: list,
    norm_w: int, norm_h: int,
    orig_w: int, orig_h: int,
) -> list:
    """정규화된 이미지 좌표 → 원본 이미지 좌표로 변환."""
    if norm_w == orig_w and norm_h == orig_h:
        return regions

    sx = orig_w / norm_w
    sy = orig_h / norm_h

    scaled = []
    for r in regions:
        scaled.append({
            "x": int(r["x"] * sx),
            "y": int(r["y"] * sy),
            "w": int(r["w"] * sx),
            "h": int(r["h"] * sy),
            "area": int(r.get("area", 0) * sx * sy),
        })
    return scaled


def save_marked_image(
    base_path: str,
    differences: list,
    output_path: str,
) -> str:
    """차이점 바운딩 박스를 원본 이미지 위에 그려서 저장."""
    SEVERITY_COLORS = {
        "critical": (220, 38, 38, 180),   # 빨강
        "major":    (234, 88, 12, 180),    # 주황
        "minor":    (202, 138, 4, 180),    # 노랑
    }

    img = Image.open(base_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for diff in differences:
        if diff.get("status") == "ignored":
            continue
        color = SEVERITY_COLORS.get(diff["severity"], (220, 38, 38, 180))
        x, y, w, h = diff["bbox_x"], diff["bbox_y"], diff["bbox_w"], diff["bbox_h"]
        draw.rectangle([x, y, x + w, y + h], outline=color[:3], width=3)
        draw.rectangle([x, y, x + w, y + h], fill=(*color[:3], 40))

    combined = Image.alpha_composite(img, overlay).convert("RGB")
    combined.save(output_path, "PNG")
    return output_path
