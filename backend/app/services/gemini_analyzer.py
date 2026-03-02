"""
Gemini Vision AI — 역할: 섹션 라벨링 + 비-간격 차이(색상, 타이포, 누락) 감지.

간격/마진/높이 측정은 CV(element_analyzer.py)가 정확하게 처리.
Gemini는 AI가 잘하는 영역에만 집중:
  1) 밴드 라벨링 — 각 UI 섹션이 무엇인지 명명
  2) 시각적 차이 — 색상, 폰트 스타일, 아이콘 누락 등
"""
from __future__ import annotations

import base64
import json
import re
from typing import Optional, List, Dict

from PIL import Image
import io
import google.generativeai as genai
from app.core.config import settings

genai.configure(api_key=settings.gemini_api_key)

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


# ──────────────────────────────────────────────────────────────
# 1단계: 밴드 라벨링 프롬프트
# ──────────────────────────────────────────────────────────────
LABELING_PROMPT = """You see a mobile screen image. I've detected {n_bands} horizontal UI sections (content bands).

The sections from top to bottom are at these Y positions:
{band_info}

For each section, tell me what UI element it is (e.g., 상태바, 헤더, 일러스트/이미지, 타이틀, 본문 텍스트, 서브텍스트, CTA 버튼, 하단 내비게이션, 입력 필드, 카드, 리스트 아이템, 구분선, 아이콘 영역, etc.)

Return ONLY a JSON array of Korean strings, one per section. No markdown, no explanation.
Example: ["상태바", "헤더", "일러스트", "타이틀", "본문 텍스트", "CTA 버튼"]"""


# ──────────────────────────────────────────────────────────────
# 2단계: 비-간격 차이 감지 프롬프트 (색상, 타이포, 누락 요소)
# ──────────────────────────────────────────────────────────────
VISUAL_DIFF_PROMPT = """You are a Design QA specialist. The DESIGN is the source of truth (spec). The DEV build must match the design.

Compare these TWO mobile screen images:
- Image 1: DESIGN mockup (디자인 시안) — 기준이 되는 정답
- Image 2: DEV build (개발 결과물) — 검증 대상

DEV image: {dev_width}×{dev_height}px.

**IMPORTANT: Do NOT report spacing/margin/padding differences.** (Those are handled separately by precise CV measurement.)

**Only find where DEV deviates from DESIGN in these categories:**
1. **color** — Background colors, text colors, button colors, icon tints that differ from design spec (provide HEX values)
2. **typography** — Font size, weight, alignment, line-height that differ from design spec
3. **missing** — Elements in design but missing in dev, or unexpected elements in dev not in design
4. **layout** — Border-radius, element width, alignment issues compared to design spec

Frame all descriptions from the DESIGN's perspective:
- "design_value" = 디자인 기준값 (the correct/intended value)
- "dev_value" = 개발 실제값 (what was actually implemented)
- Description should say what the design specifies and how dev deviates

Return ONLY a JSON array. No markdown fences.
Each item:
{{"category":"color"|"typography"|"missing"|"layout","severity":"critical"|"major"|"minor","description":"한국어 설명 — 디자인 기준 X, 개발에서 Y로 다름","design_value":"기준값","dev_value":"실제값","bbox_x":int,"bbox_y":int,"bbox_w":int,"bbox_h":int}}

Find 0~10 differences. If no differences in these categories, return [].
"""


def _img_to_bytes(img_path: str, max_dim: int = 2048) -> bytes:
    """이미지를 로드. 작은 이미지는 원본 그대로 전송."""
    img = Image.open(img_path).convert("RGB")
    if max(img.width, img.height) <= 1000:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    if max(img.width, img.height) > max_dim:
        ratio = max_dim / max(img.width, img.height)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _call_gemini(prompt: str, image_parts: list) -> Optional[str]:
    """Gemini 모델 체인 호출."""
    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"[Gemini] 모델 시도: {model_name}")
            model = genai.GenerativeModel(model_name)
            content = [prompt] + image_parts
            response = model.generate_content(
                content,
                generation_config={"temperature": 0.1, "max_output_tokens": 4096},
            )
            raw = response.text.strip()
            print(f"[Gemini] {model_name} 응답: {len(raw)}자 — {raw[:150]}")
            return raw
        except Exception as e:
            last_error = e
            print(f"[Gemini] {model_name} 실패: {e}")
            continue
    print(f"[Gemini] 모든 모델 실패: {last_error}")
    return None


def _parse_json(raw: str) -> Optional[list]:
    """JSON 배열을 강건하게 파싱."""
    if not raw:
        return None

    cleaned = raw.strip()
    # 마크다운 코드 펜스 제거
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # [ ... ] 추출
    start = cleaned.find('[')
    end = cleaned.rfind(']')
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass

    print(f"[Gemini] JSON 파싱 실패: {raw[:200]}")
    return None


async def label_bands(
    dev_path: str,
    bands: List[Dict],
) -> Optional[List[str]]:
    """
    Gemini를 사용하여 감지된 밴드에 의미론적 라벨 부여.
    Returns: ["상태바", "헤더", "일러스트", ...] 또는 None
    """
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        return None
    if not bands:
        return None

    dev_bytes = _img_to_bytes(dev_path)
    dev_part = {"mime_type": "image/png", "data": base64.b64encode(dev_bytes).decode()}

    band_info = "\n".join(
        f"  Section {i+1}: y={b['y_start']}~{b['y_end']} (height={b['height']}px, "
        f"left_margin={b['left_margin']}px, right_margin={b['right_margin']}px)"
        for i, b in enumerate(bands)
    )

    prompt = LABELING_PROMPT.format(n_bands=len(bands), band_info=band_info)

    print("[Gemini] 밴드 라벨링 시작")
    raw = _call_gemini(prompt, [dev_part])
    if not raw:
        return None

    parsed = _parse_json(raw)
    if parsed and isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
        print(f"[Gemini] 라벨: {parsed}")
        return parsed

    return None


async def find_visual_diffs(
    design_path: str,
    dev_path: str,
    dev_width: int,
    dev_height: int,
) -> List[Dict]:
    """
    색상, 타이포, 누락 요소 등 비-간격 차이를 감지.
    (간격은 CV가 처리하므로 여기서는 제외)
    """
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        return []

    design_bytes = _img_to_bytes(design_path)
    dev_bytes = _img_to_bytes(dev_path)

    design_part = {"mime_type": "image/png", "data": base64.b64encode(design_bytes).decode()}
    dev_part = {"mime_type": "image/png", "data": base64.b64encode(dev_bytes).decode()}

    prompt = VISUAL_DIFF_PROMPT.format(dev_width=dev_width, dev_height=dev_height)

    print("[Gemini] 시각적 차이 분석 시작 (색상/타이포/누락)")
    raw = _call_gemini(prompt, [design_part, dev_part])
    if not raw:
        return []

    parsed = _parse_json(raw)
    if not parsed:
        return []

    # 유효성 검증
    VALID_CATEGORIES = {"typography", "color", "layout", "missing"}
    VALID_SEVERITIES = {"critical", "major", "minor"}
    valid = []

    for d in parsed:
        if not isinstance(d, dict):
            continue
        if "description" not in d:
            continue

        cat = str(d.get("category", "layout")).lower().strip()
        if cat not in VALID_CATEGORIES:
            cat = "layout"
        # spacing 카테고리가 들어오면 건너뛰기 (CV가 처리)
        if cat == "spacing":
            continue

        sev = str(d.get("severity", "minor")).lower().strip()
        if sev not in VALID_SEVERITIES:
            sev = "minor"

        def safe_int(val, default=0):
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return default

        valid.append({
            "category": cat,
            "severity": sev,
            "description": str(d.get("description", "")),
            "design_value": str(d.get("design_value", "")),
            "dev_value": str(d.get("dev_value", "")),
            "bbox_x": max(0, min(dev_width - 10, safe_int(d.get("bbox_x")))),
            "bbox_y": max(0, min(dev_height - 10, safe_int(d.get("bbox_y")))),
            "bbox_w": max(10, min(dev_width, safe_int(d.get("bbox_w"), 50))),
            "bbox_h": max(10, min(dev_height, safe_int(d.get("bbox_h"), 30))),
        })

    print(f"[Gemini] 시각적 차이: {len(valid)}개")
    return valid


# ──────────────────────────────────────────────────────────────
# 3단계: 미커버 영역 타겟 분석 (pixel diff가 찾았지만 CV가 못 잡은 영역)
# ──────────────────────────────────────────────────────────────
TARGETED_DIFF_PROMPT = """You are a Design QA specialist examining a SPECIFIC region where pixel differences were detected.

Compare these TWO cropped regions:
- Image 1: DESIGN mockup (디자인 시안) — 기준
- Image 2: DEV build (개발 결과물) — 검증 대상

The region is at position ({rx}, {ry}) with size {rw}×{rh}px in the full {dev_width}×{dev_height}px screen.

Analyze what is different in this specific region. Possible differences:
1. **spacing** — Element positions shifted, gaps differ (provide px values)
2. **layout** — Element sizes differ, alignment issues
3. **color** — Colors differ (provide HEX)
4. **typography** — Font size/weight/style differs
5. **missing** — Elements present in one but not the other

Return ONLY a JSON array. If genuinely identical, return [].
Each item:
{{"category":"spacing"|"layout"|"color"|"typography"|"missing","severity":"critical"|"major"|"minor","description":"한국어 설명","design_value":"기준값","dev_value":"실제값"}}

Find the most significant difference in this region. Return at most 1-2 items."""


def _crop_to_bytes(img_path: str, region: dict, padding: int = 20) -> Optional[bytes]:
    """이미지에서 특정 영역을 크롭하여 PNG bytes로 반환."""
    img = Image.open(img_path).convert("RGB")
    x1 = max(0, region["x"] - padding)
    y1 = max(0, region["y"] - padding)
    x2 = min(img.width, region["x"] + region["w"] + padding)
    y2 = min(img.height, region["y"] + region["h"] + padding)

    if x2 - x1 < 10 or y2 - y1 < 10:
        return None

    cropped = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


async def analyze_uncovered_regions(
    design_path: str,
    dev_path: str,
    uncovered_regions: List[Dict],
    dev_width: int,
    dev_height: int,
    max_regions: int = 5,
) -> List[Dict]:
    """
    pixel diff가 감지했지만 CV가 커버하지 못한 영역을 Gemini에 크롭하여 분석.
    전체 이미지 대신 특정 영역만 보내므로 정밀도가 높다.
    """
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key_here":
        return []
    if not uncovered_regions:
        return []

    # 면적 큰 순으로 정렬, 상위 N개만 분석 (API 비용 절감)
    sorted_regions = sorted(uncovered_regions, key=lambda r: r.get("area", 0), reverse=True)
    targets = sorted_regions[:max_regions]

    all_diffs: List[Dict] = []

    for region in targets:
        design_crop = _crop_to_bytes(design_path, region)
        dev_crop = _crop_to_bytes(dev_path, region)
        if not design_crop or not dev_crop:
            continue

        design_part = {"mime_type": "image/png", "data": base64.b64encode(design_crop).decode()}
        dev_part = {"mime_type": "image/png", "data": base64.b64encode(dev_crop).decode()}

        prompt = TARGETED_DIFF_PROMPT.format(
            rx=region["x"], ry=region["y"],
            rw=region["w"], rh=region["h"],
            dev_width=dev_width, dev_height=dev_height,
        )

        print(f"[Gemini] 타겟 분석: ({region['x']},{region['y']}) {region['w']}×{region['h']}px")
        raw = _call_gemini(prompt, [design_part, dev_part])
        if not raw:
            continue

        parsed = _parse_json(raw)
        if not parsed:
            continue

        VALID_CATEGORIES = {"typography", "color", "layout", "missing", "spacing"}
        VALID_SEVERITIES = {"critical", "major", "minor"}

        for d in parsed:
            if not isinstance(d, dict) or "description" not in d:
                continue

            cat = str(d.get("category", "layout")).lower().strip()
            if cat not in VALID_CATEGORIES:
                cat = "layout"

            sev = str(d.get("severity", "minor")).lower().strip()
            if sev not in VALID_SEVERITIES:
                sev = "minor"

            all_diffs.append({
                "category": cat,
                "severity": sev,
                "description": str(d.get("description", "")),
                "design_value": str(d.get("design_value", "")),
                "dev_value": str(d.get("dev_value", "")),
                "bbox_x": region["x"],
                "bbox_y": region["y"],
                "bbox_w": region["w"],
                "bbox_h": region["h"],
            })

    print(f"[Gemini] 타겟 분석 결과: {len(all_diffs)}개 (미커버 {len(targets)}개 영역)")
    return all_diffs
