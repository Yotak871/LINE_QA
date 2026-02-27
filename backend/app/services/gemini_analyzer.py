import base64
import json
import re
import numpy as np
from PIL import Image
import io
import google.generativeai as genai
from app.core.config import settings

genai.configure(api_key=settings.gemini_api_key)

# 모델 폴백 체인 — 할당량 초과 시 다음 모델로 자동 전환
GEMINI_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
]


# ──────────────────────────────────────────────────────────────
# Gemini Vision 프롬프트 — 디자인 QA 전문가
# ──────────────────────────────────────────────────────────────
ANALYSIS_PROMPT = """You are an expert UI/UX Design QA auditor for a mobile app team.

You will receive TWO images of the same mobile screen:
- **Image 1**: The DESIGN original (디자인 원본 - created by UI designer)
- **Image 2**: The DEV build (개발 Beta 버전 - actual implementation)

Your job: Meticulously compare these two screens and find ALL visual differences.

**Focus areas (check every one):**
1. **spacing** — margins, padding, gaps between elements (px differences)
2. **typography** — font size, font weight, line-height, letter-spacing, text content differences
3. **color** — background colors, text colors, border colors, button colors
4. **layout** — element sizes (width/height), positions, alignment, border-radius
5. **missing** — elements present in design but absent in dev, or vice versa

**Bounding box coordinates:**
The DEV build image (Image 2) has dimensions {dev_width}×{dev_height} pixels.
For each difference, provide the bounding box in PIXEL coordinates relative to the DEV image:
- bbox_x: X position of the left edge (0 = left side of image)
- bbox_y: Y position of the top edge (0 = top of image)
- bbox_w: width of the bounding box
- bbox_h: height of the bounding box

**Return format: JSON array only, NO markdown, NO explanation.**
Each item in the array:
{{
  "category": "spacing" | "typography" | "color" | "layout" | "missing",
  "severity": "critical" | "major" | "minor",
  "description": "한국어로 구체적인 설명 (어떤 요소가 정확히 어떻게 다른지)",
  "design_value": "디자인 원본의 정확한 값",
  "dev_value": "개발 버전의 정확한 값",
  "bbox_x": integer,
  "bbox_y": integer,
  "bbox_w": integer,
  "bbox_h": integer
}}

**Severity guide:**
- **critical**: 요소 누락, 레이아웃 완전히 깨짐, 잘못된 텍스트/이미지
- **major**: 눈에 띄는 차이 (간격 >5px, 색상 차이 뚜렷, 폰트 크기 ±2px 이상)
- **minor**: 미세한 차이 (간격 ≤4px, 미세한 색상 차이, 라운드 코너 차이)

**Rules:**
- Find 3~15 meaningful differences (모바일 화면이므로 꼼꼼히 비교)
- Be SPECIFIC: "CTA 버튼과 하단 면책조항 텍스트 사이 간격이 24px이어야 하는데 16px입니다" (NOT "간격이 다릅니다")
- Include CONCRETE values: pixel sizes, hex color codes, font specs
- Bounding box must tightly surround the SPECIFIC element that is different
- If text content differs between languages (localization), that's NOT a difference — focus on VISUAL/LAYOUT differences only
"""


def _img_to_bytes(img_path: str, max_dim: int = 1024) -> bytes:
    """이미지를 로드하고 Gemini용으로 적절한 크기로 리사이즈."""
    img = Image.open(img_path).convert("RGB")
    # 너무 큰 이미지는 리사이즈 (토큰 절약 + 속도 향상)
    if max(img.width, img.height) > max_dim:
        ratio = max_dim / max(img.width, img.height)
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _get_image_dimensions(img_path: str) -> tuple:
    """이미지의 원본 크기를 반환."""
    img = Image.open(img_path)
    return img.width, img.height


async def analyze_with_gemini(
    design_path: str,
    dev_path: str,
    regions: list,
    dev_width: int,
    dev_height: int,
) -> list:
    """Gemini Vision API로 두 이미지를 비교 분석한다. 모델 폴백 체인 사용."""
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        return _mock_analysis(regions, dev_width, dev_height)

    # 두 이미지를 준비
    design_bytes = _img_to_bytes(design_path, max_dim=1280)
    dev_bytes = _img_to_bytes(dev_path, max_dim=1280)

    design_part = {"mime_type": "image/png", "data": base64.b64encode(design_bytes).decode()}
    dev_part = {"mime_type": "image/png", "data": base64.b64encode(dev_bytes).decode()}

    # 프롬프트에 이미지 크기 정보 삽입
    prompt = ANALYSIS_PROMPT.format(dev_width=dev_width, dev_height=dev_height)

    # 픽셀 diff 영역 힌트 추가 (Gemini에게 참고 정보)
    if regions:
        hint_regions = [{"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]} for r in regions[:8]]
        prompt += f"\n\n**Pixel diff detected these regions (reference only, find all differences yourself):**\n{json.dumps(hint_regions)}"

    # 모델 폴백 체인: 순서대로 시도
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"[Gemini] 모델 시도: {model_name}")
            model = genai.GenerativeModel(model_name)

            response = model.generate_content(
                [prompt, design_part, dev_part],
                generation_config={"temperature": 0.2, "max_output_tokens": 4096},
            )
            raw = response.text.strip()
            print(f"[Gemini] {model_name} 응답 길이: {len(raw)}자")

            # JSON 파싱 (markdown 코드블록 제거)
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            differences = json.loads(raw)

            if not isinstance(differences, list):
                print(f"[Gemini] {model_name} 응답이 배열이 아닙니다. 다음 모델 시도.")
                continue

            validated = _validate_differences(differences, dev_width, dev_height)
            print(f"[Gemini] {model_name} 분석 완료: {len(validated)}개 차이점 발견")
            return validated

        except Exception as e:
            last_error = e
            err_str = str(e)
            print(f"[Gemini] {model_name} 실패: {err_str}")

            # 429 (할당량 초과)인 경우 다음 모델로 시도
            if "429" in err_str or "quota" in err_str.lower():
                print(f"[Gemini] 할당량 초과. 다음 모델로 전환합니다.")
                continue
            # 그 외 에러도 다음 모델 시도
            continue

    print(f"[Gemini] 모든 모델 실패. pixel diff 결과로 대체합니다. 마지막 에러: {last_error}")
    return _fallback_from_regions(regions, dev_width, dev_height)


def _validate_differences(diffs: list, dev_w: int, dev_h: int) -> list:
    """Gemini 응답 유효성 검증 및 정규화."""
    VALID_CATEGORIES = {"typography", "color", "spacing", "layout", "missing"}
    VALID_SEVERITIES = {"critical", "major", "minor"}
    valid = []

    for d in diffs:
        if not isinstance(d, dict):
            continue
        if not all(k in d for k in ["category", "severity", "description"]):
            continue

        d["category"] = str(d.get("category", "layout")).lower()
        d["severity"] = str(d.get("severity", "minor")).lower()

        if d["category"] not in VALID_CATEGORIES:
            d["category"] = "layout"
        if d["severity"] not in VALID_SEVERITIES:
            d["severity"] = "minor"

        # bbox 좌표 검증 및 클램핑
        bbox_x = max(0, min(dev_w - 10, int(d.get("bbox_x", 0))))
        bbox_y = max(0, min(dev_h - 10, int(d.get("bbox_y", 0))))
        bbox_w = max(20, min(dev_w - bbox_x, int(d.get("bbox_w", 50))))
        bbox_h = max(20, min(dev_h - bbox_y, int(d.get("bbox_h", 50))))

        d["bbox_x"] = bbox_x
        d["bbox_y"] = bbox_y
        d["bbox_w"] = bbox_w
        d["bbox_h"] = bbox_h
        d["design_value"] = str(d.get("design_value", ""))
        d["dev_value"] = str(d.get("dev_value", ""))
        d["description"] = str(d.get("description", ""))

        valid.append(d)

    return valid


def _fallback_from_regions(regions: list, dev_w: int, dev_h: int) -> list:
    """Gemini 실패 시 픽셀 차이 영역을 기반으로 기본 항목 생성."""
    if not regions:
        return [{
            "category": "layout",
            "severity": "major",
            "description": "전체 화면에서 픽셀 차이가 감지되었습니다. 세부 항목은 수동 확인이 필요합니다.",
            "design_value": "",
            "dev_value": "",
            "bbox_x": int(dev_w * 0.05),
            "bbox_y": int(dev_h * 0.05),
            "bbox_w": int(dev_w * 0.9),
            "bbox_h": int(dev_h * 0.9),
        }]

    result = []
    total_area = dev_w * dev_h

    for i, r in enumerate(regions[:12]):
        r_area = r["w"] * r["h"]
        area_pct = (r_area / total_area) * 100 if total_area > 0 else 0

        # 위치 기반 카테고리 추정
        center_y_pct = (r["y"] + r["h"] / 2) / dev_h
        aspect_ratio = r["w"] / max(r["h"], 1)

        if aspect_ratio > 3 and r["h"] < dev_h * 0.05:
            category = "spacing"
            location = "수평 간격/여백"
        elif aspect_ratio < 0.3 and r["w"] < dev_w * 0.05:
            category = "spacing"
            location = "수직 간격/여백"
        elif r["w"] > dev_w * 0.6 and r["h"] < dev_h * 0.08:
            category = "typography"
            location = "텍스트 영역"
        elif r["w"] < dev_w * 0.15 and r["h"] < dev_h * 0.04:
            category = "color"
            location = "아이콘/색상"
        else:
            category = "layout"
            location = "UI 요소"

        # 위치 설명
        if center_y_pct < 0.15:
            pos = "상단 (헤더/내비게이션)"
        elif center_y_pct < 0.4:
            pos = "상단 콘텐츠 영역"
        elif center_y_pct < 0.7:
            pos = "중앙 콘텐츠 영역"
        elif center_y_pct < 0.85:
            pos = "하단 콘텐츠 영역"
        else:
            pos = "하단 (푸터/CTA)"

        if area_pct > 5:
            severity = "critical"
            desc = f"{pos}의 {location}에서 큰 차이 감지 — 화면의 {area_pct:.1f}% 영역. 수동 확인 필요"
        elif area_pct > 1:
            severity = "major"
            desc = f"{pos}의 {location}에서 눈에 띄는 차이 감지 — 요소의 크기·위치·스타일이 다를 수 있습니다"
        else:
            severity = "minor"
            desc = f"{pos}의 {location}에서 미세한 차이 감지 — 간격·색상·스타일의 미세한 차이"

        result.append({
            "category": category,
            "severity": severity,
            "description": desc,
            "design_value": f"영역: {r['w']}×{r['h']}px",
            "dev_value": f"위치: ({r['x']},{r['y']})",
            "bbox_x": r["x"],
            "bbox_y": r["y"],
            "bbox_w": r["w"],
            "bbox_h": r["h"],
        })
    return result


def _mock_analysis(regions: list, dev_w: int, dev_h: int) -> list:
    """API 키 없을 때 목업 데이터 반환."""
    return [
        {
            "category": "spacing",
            "severity": "major",
            "description": "[Mock] 타이틀과 서브텍스트 사이 간격이 24px이어야 하는데 16px입니다.",
            "design_value": "24px",
            "dev_value": "16px",
            "bbox_x": int(dev_w * 0.1),
            "bbox_y": int(dev_h * 0.35),
            "bbox_w": int(dev_w * 0.8),
            "bbox_h": int(dev_h * 0.05),
        },
        {
            "category": "layout",
            "severity": "critical",
            "description": "[Mock] CTA 버튼 너비가 디자인과 다릅니다. 좌우 16px 여백 기준이어야 합니다.",
            "design_value": f"{dev_w - 32}px",
            "dev_value": f"{dev_w}px (전체 폭)",
            "bbox_x": 0,
            "bbox_y": int(dev_h * 0.85),
            "bbox_w": dev_w,
            "bbox_h": int(dev_h * 0.07),
        },
        {
            "category": "color",
            "severity": "minor",
            "description": "[Mock] 배경색이 약간 다릅니다.",
            "design_value": "#F8FAFC",
            "dev_value": "#FFF1F2",
            "bbox_x": 0,
            "bbox_y": 0,
            "bbox_w": dev_w,
            "bbox_h": int(dev_h * 0.15),
        },
    ]
