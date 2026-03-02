"use client";

import { useState, useRef, useEffect } from "react";
import { Layers, SplitSquareHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import type { Difference, ImageSize } from "@/lib/types";

/* ─── 심각도별 색상 ─────────────────────────────────────── */
const SEVERITY_STROKE: Record<string, string> = {
  critical: "#e02000",
  major:    "#ea580c",
  minor:    "#ca8a04",
};

/* 배지 색상 */
const BADGE_BG = "#06c755";
const BADGE_ACTIVE_BG = "#e02000";

interface Props {
  designUrl:        string;
  devUrl:           string;
  differences:      Difference[];
  activeDiffId:     string | null;
  hoveredDiffId?:   string | null;
  onSelectDiff:     (id: string) => void;
  devImageSize?:    ImageSize;
  designImageSize?: ImageSize;
}

type ViewMode = "sidebyside" | "overlay";

export default function ImageViewer({
  designUrl, devUrl, differences, activeDiffId, hoveredDiffId, onSelectDiff,
  devImageSize, designImageSize,
}: Props) {
  const [mode, setMode]       = useState<ViewMode>("sidebyside");
  const [sliderX, setSliderX] = useState(50);
  const [zoom, setZoom]       = useState(1);

  const visibleDiffs = differences.filter((d) => d.status !== "ignored");
  const numberedDiffs = visibleDiffs.map((d, i) => ({ ...d, num: i + 1 }));

  /* 포커스 대상: 클릭 > 호버 > 없음 */
  const focusId = activeDiffId ?? hoveredDiffId ?? null;

  const handleOverlayMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    setSliderX(Math.max(5, Math.min(95, ((e.clientX - r.left) / r.width) * 100)));
  };

  return (
    <div className="flex flex-col h-full gap-3">
      {/* ── 툴바 ── */}
      <div className="flex items-center justify-between px-1">
        <div className="flex gap-1 bg-surface-50 rounded-lg p-1 border border-surface-100">
          {([
            { key: "sidebyside", icon: SplitSquareHorizontal, label: "나란히 보기" },
            { key: "overlay",    icon: Layers,                label: "슬라이더 비교" },
          ] as const).map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              onClick={() => setMode(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                mode === key
                  ? "bg-white shadow-sm text-[#111] border border-surface-100"
                  : "text-[#999] hover:text-[#616161]"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <button onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}
            className="p-1.5 rounded hover:bg-surface-50 text-[#999]"><ZoomOut size={14} /></button>
          <span className="text-xs text-[#999] w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom(z => Math.min(4, z + 0.25))}
            className="p-1.5 rounded hover:bg-surface-50 text-[#999]"><ZoomIn size={14} /></button>
        </div>
      </div>

      {/* ── 뷰어 ── */}
      <div className="flex-1 overflow-auto bg-surface-50 rounded-xl border border-surface-100">
        {mode === "sidebyside" ? (
          <div className="flex gap-4 p-4 min-w-max">
            <AnnotatedImage
              url={designUrl}
              label="디자인"
              labelCls="bg-blue-50 text-blue-700 border border-blue-200"
              diffs={numberedDiffs}
              focusId={focusId}
              activeDiffId={activeDiffId}
              onSelect={onSelectDiff}
              zoom={zoom}
              imageSize={designImageSize}
              sourceImageSize={devImageSize}
              showDesignValue
            />
            <AnnotatedImage
              url={devUrl}
              label="개발"
              labelCls="bg-line-50 text-line-700 border border-line-200"
              diffs={numberedDiffs}
              focusId={focusId}
              activeDiffId={activeDiffId}
              onSelect={onSelectDiff}
              zoom={zoom}
              imageSize={devImageSize}
              showDevValue
            />
          </div>
        ) : (
          <div className="p-4">
            <OverlayView
              devUrl={devUrl}
              designUrl={designUrl}
              diffs={numberedDiffs}
              focusId={focusId}
              activeDiffId={activeDiffId}
              onSelect={onSelectDiff}
              sliderX={sliderX}
              onMouseMove={handleOverlayMove}
              zoom={zoom}
              imageSize={devImageSize}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   AnnotatedImage — Single Focus Mode

   포커스된 항목만 하이라이트 + 뱃지 + 값 표시
   비포커스 항목은 아무것도 표시하지 않음 (깨끗한 이미지)
═══════════════════════════════════════════════════════════ */
function AnnotatedImage({
  url, label, labelCls, diffs, focusId, activeDiffId, onSelect, zoom,
  imageSize, sourceImageSize,
  showDesignValue, showDevValue,
}: {
  url: string;
  label: string;
  labelCls: string;
  diffs: Array<Difference & { num: number }>;
  focusId: string | null;
  activeDiffId: string | null;
  onSelect: (id: string) => void;
  zoom: number;
  imageSize?: ImageSize;
  sourceImageSize?: ImageSize;
  showDesignValue?: boolean;
  showDevValue?: boolean;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const onLoad = () => setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    if (img.complete) onLoad();
    else img.addEventListener("load", onLoad);
    return () => img.removeEventListener("load", onLoad);
  }, [url]);

  const vw = imageSize?.width  ?? naturalSize?.w ?? 0;
  const vh = imageSize?.height ?? naturalSize?.h ?? 0;

  const scaleX = sourceImageSize && imageSize
    ? imageSize.width / sourceImageSize.width : 1;
  const scaleY = sourceImageSize && imageSize
    ? imageSize.height / sourceImageSize.height : 1;

  const BADGE_R = vw > 0 ? Math.max(12, Math.min(18, vw * 0.032)) : 14;

  return (
    <div className="flex flex-col gap-2 shrink-0">
      <span className={`text-xs font-semibold px-2.5 py-1 rounded-full self-start ${labelCls}`}>
        {label}
      </span>
      <div className="relative inline-block"
        style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }}>
        <img ref={imgRef} src={url} alt={label}
          className="block max-w-full rounded-lg shadow-sm" draggable={false} />

        {vw > 0 && vh > 0 && (
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox={`0 0 ${vw} ${vh}`}
            preserveAspectRatio="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ pointerEvents: "none", overflow: "visible" }}
          >
            {diffs.map((d) => {
              const isFocused  = focusId === d.id;
              const isActive   = activeDiffId === d.id;

              // 디자인 패널: design_bbox가 유효하면 직접 사용 (원본 디자인 좌표)
              // 유효하지 않으면 (이전 데이터, 0값) bbox에 스케일 적용으로 fallback
              const hasDesignBbox = showDesignValue
                && d.design_bbox_w != null && d.design_bbox_h != null
                && d.design_bbox_w > 0 && d.design_bbox_h > 0;
              const bx = hasDesignBbox ? d.design_bbox_x! : d.bbox_x * scaleX;
              const by = hasDesignBbox ? d.design_bbox_y! : d.bbox_y * scaleY;
              const bw = hasDesignBbox ? d.design_bbox_w! : d.bbox_w * scaleX;
              const bh = hasDesignBbox ? d.design_bbox_h! : d.bbox_h * scaleY;

              const stroke = SEVERITY_STROKE[d.severity] ?? "#e02000";

              /* ── 포커스되지 않은 항목: 아무것도 표시하지 않음 ── */
              if (!isFocused) return <g key={d.id} />;

              /* ── 포커스된 항목: 풀 하이라이트 + 뱃지 + 값 ── */
              const fillColor = isActive ? "rgba(6,199,85,0.18)" : "rgba(224,32,0,0.10)";
              const strokeColor = isActive ? "#06c755" : stroke;
              const sw = isActive ? 3 : 2.5;

              const badgeCx = bx - BADGE_R * 0.35;
              const badgeCy = by - BADGE_R * 0.35;
              const badgeFill = isActive ? BADGE_ACTIVE_BG : BADGE_BG;

              const valLabel = showDesignValue ? d.design_value
                : showDevValue ? d.dev_value : null;
              const fontSize = Math.max(10, vw * 0.024);

              return (
                <g key={d.id} style={{ pointerEvents: "all", cursor: "pointer" }}
                  onClick={() => onSelect(d.id)}>
                  {/* 하이라이트 영역 */}
                  <rect x={bx} y={by} width={bw} height={bh}
                    fill={fillColor} stroke={strokeColor} strokeWidth={sw}
                    rx={4} strokeDasharray={isActive ? "none" : "6 3"} />

                  {/* 값 라벨 (영역 중앙) */}
                  {valLabel && (
                    <g>
                      <rect
                        x={bx + bw / 2 - Math.max(valLabel.length * 4, 18)}
                        y={by + bh / 2 - fontSize * 0.7}
                        width={Math.max(valLabel.length * 8, 36)}
                        height={fontSize * 1.6}
                        rx={4} fill={strokeColor} opacity={0.88} />
                      <text x={bx + bw / 2} y={by + bh / 2 + fontSize * 0.35}
                        textAnchor="middle" fontSize={fontSize}
                        fontWeight={700} fill="white">
                        {valLabel}
                      </text>
                    </g>
                  )}

                  {/* 넘버 배지 */}
                  <circle cx={badgeCx} cy={badgeCy + 1} r={BADGE_R + 1}
                    fill="rgba(0,0,0,0.18)" />
                  <circle cx={badgeCx} cy={badgeCy} r={BADGE_R}
                    fill={badgeFill} stroke="white" strokeWidth={2.5} />
                  <text x={badgeCx} y={badgeCy + BADGE_R * 0.36}
                    textAnchor="middle" fontSize={BADGE_R * 0.95}
                    fontWeight={800} fill="white">
                    {d.num}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   OverlayView — 슬라이더 비교 모드 (동일한 포커스 로직)
═══════════════════════════════════════════════════════════ */
function OverlayView({
  devUrl, designUrl, diffs, focusId, activeDiffId, onSelect,
  sliderX, onMouseMove, zoom, imageSize,
}: {
  devUrl: string; designUrl: string;
  diffs: Array<Difference & { num: number }>;
  focusId: string | null;
  activeDiffId: string | null;
  onSelect: (id: string) => void;
  sliderX: number;
  onMouseMove: (e: React.MouseEvent<HTMLDivElement>) => void;
  zoom: number;
  imageSize?: ImageSize;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const onLoad = () => setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    if (img.complete) onLoad();
    else img.addEventListener("load", onLoad);
    return () => img.removeEventListener("load", onLoad);
  }, [devUrl]);

  const vw = imageSize?.width  ?? naturalSize?.w ?? 0;
  const vh = imageSize?.height ?? naturalSize?.h ?? 0;
  const BADGE_R = vw > 0 ? Math.max(12, Math.min(18, vw * 0.032)) : 14;

  return (
    <div className="relative select-none cursor-col-resize inline-block rounded-lg overflow-hidden shadow-sm"
      style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }}
      onMouseMove={onMouseMove}>
      <img ref={imgRef} src={devUrl} alt="dev" className="block max-w-full" draggable={false} />
      <div className="absolute inset-0 overflow-hidden" style={{ width: `${sliderX}%` }}>
        <img src={designUrl} alt="design" className="block max-w-none"
          style={{ width: `${10000 / sliderX}%` }} draggable={false} />
      </div>

      <div className="absolute top-0 bottom-0 w-0.5 bg-white shadow-md pointer-events-none"
        style={{ left: `${sliderX}%` }}>
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-7 h-7 bg-white rounded-full shadow-lg flex items-center justify-center text-[#999] text-xs font-bold">⇔</div>
      </div>

      {vw > 0 && vh > 0 && (
        <svg className="absolute inset-0 w-full h-full"
          viewBox={`0 0 ${vw} ${vh}`} preserveAspectRatio="none"
          style={{ pointerEvents: "none", overflow: "visible" }}>
          {diffs.map((d) => {
            const isFocused = focusId === d.id;
            const isActive  = activeDiffId === d.id;
            const stroke = SEVERITY_STROKE[d.severity] ?? "#e02000";

            if (!isFocused) return <g key={d.id} />;

            const fillColor = isActive ? "rgba(6,199,85,0.18)" : "rgba(224,32,0,0.10)";
            const strokeColor = isActive ? "#06c755" : stroke;
            const badgeCx = d.bbox_x - BADGE_R * 0.35;
            const badgeCy = d.bbox_y - BADGE_R * 0.35;

            return (
              <g key={d.id} style={{ pointerEvents: "all", cursor: "pointer" }}
                onClick={() => onSelect(d.id)}>
                <rect x={d.bbox_x} y={d.bbox_y} width={d.bbox_w} height={d.bbox_h}
                  fill={fillColor} stroke={strokeColor} strokeWidth={2.5} rx={4} />
                <circle cx={badgeCx} cy={badgeCy + 1} r={BADGE_R + 1}
                  fill="rgba(0,0,0,0.18)" />
                <circle cx={badgeCx} cy={badgeCy} r={BADGE_R}
                  fill={isActive ? BADGE_ACTIVE_BG : BADGE_BG}
                  stroke="white" strokeWidth={2.5} />
                <text x={badgeCx} y={badgeCy + BADGE_R * 0.36}
                  textAnchor="middle" fontSize={BADGE_R * 0.95}
                  fontWeight={800} fill="white">
                  {d.num}
                </text>
              </g>
            );
          })}
        </svg>
      )}

      <div className="absolute top-2 left-2 bg-line-50 text-line-700 text-xs px-2 py-0.5 rounded-full font-semibold pointer-events-none border border-line-200">개발</div>
      <div className="absolute top-2 right-2 bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full font-semibold pointer-events-none border border-blue-200">디자인</div>
    </div>
  );
}
