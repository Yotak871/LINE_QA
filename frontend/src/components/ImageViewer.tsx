"use client";

import { useState, useRef, useEffect } from "react";
import { Layers, SplitSquareHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import type { Difference, ImageSize } from "@/lib/types";

/* ─── 심각도별 색상 ─────────────────────────────────────── */
const SEVERITY_FILL: Record<string, string> = {
  critical: "rgba(224,32,0,0.14)",
  major:    "rgba(234,88,12,0.14)",
  minor:    "rgba(202,138,4,0.10)",
};
const SEVERITY_STROKE: Record<string, string> = {
  critical: "#e02000",
  major:    "#ea580c",
  minor:    "#ca8a04",
};

/* 번호 배지 색상 — LINE green 기반 */
const BADGE_BG = "#06c755";
const BADGE_ACTIVE_BG = "#e02000";
const BADGE_APPROVED_BG = "#06c755";

interface Props {
  designUrl:        string;
  devUrl:           string;
  differences:      Difference[];
  activeDiffId:     string | null;
  onSelectDiff:     (id: string) => void;
  devImageSize?:    ImageSize;
  designImageSize?: ImageSize;
}

type ViewMode = "sidebyside" | "overlay";

export default function ImageViewer({
  designUrl, devUrl, differences, activeDiffId, onSelectDiff,
  devImageSize, designImageSize,
}: Props) {
  const [mode, setMode]       = useState<ViewMode>("sidebyside");
  const [sliderX, setSliderX] = useState(50);
  const [zoom, setZoom]       = useState(1);

  const visibleDiffs = differences.filter((d) => d.status !== "ignored");
  const numberedDiffs = visibleDiffs.map((d, i) => ({ ...d, num: i + 1 }));

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
              url={devUrl}
              label="Beta (개발)"
              labelCls="bg-line-50 text-line-700 border border-line-200"
              diffs={numberedDiffs}
              activeDiffId={activeDiffId}
              onSelect={onSelectDiff}
              zoom={zoom}
              imageSize={devImageSize}
              showCurrentValue
            />
            <AnnotatedImage
              url={designUrl}
              label="Design (원본)"
              labelCls="bg-surface-50 text-[#616161] border border-surface-200"
              diffs={numberedDiffs}
              activeDiffId={activeDiffId}
              onSelect={onSelectDiff}
              zoom={zoom}
              imageSize={designImageSize}
              sourceImageSize={devImageSize}
              showTargetValue
            />
          </div>
        ) : (
          <div className="p-4">
            <OverlayView
              devUrl={devUrl}
              designUrl={designUrl}
              diffs={numberedDiffs}
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
   AnnotatedImage — SVG viewBox로 원본 좌표 → 표시 크기 자동 매핑
═══════════════════════════════════════════════════════════ */
function AnnotatedImage({
  url, label, labelCls, diffs, activeDiffId, onSelect, zoom,
  imageSize, sourceImageSize,
  showCurrentValue, showTargetValue,
}: {
  url: string;
  label: string;
  labelCls: string;
  diffs: Array<Difference & { num: number }>;
  activeDiffId: string | null;
  onSelect: (id: string) => void;
  zoom: number;
  imageSize?: ImageSize;
  sourceImageSize?: ImageSize;
  showCurrentValue?: boolean;
  showTargetValue?: boolean;
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

  /* viewBox 크기: API 크기 > naturalSize > 0 */
  const vw = imageSize?.width  ?? naturalSize?.w ?? 0;
  const vh = imageSize?.height ?? naturalSize?.h ?? 0;

  /* Design 이미지용 좌표 스케일링 (dev 기준 bbox → design 비율 변환) */
  const scaleX = sourceImageSize && imageSize
    ? imageSize.width / sourceImageSize.width : 1;
  const scaleY = sourceImageSize && imageSize
    ? imageSize.height / sourceImageSize.height : 1;

  /* 배지 크기 (viewBox 비율 기준) */
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
            style={{ pointerEvents: "none" }}
          >
            {diffs.map((d) => {
              const isActive   = activeDiffId === d.id;
              const isApproved = d.status === "approved";
              const fill   = isActive ? "rgba(6,199,85,0.18)" : SEVERITY_FILL[d.severity];
              const stroke = isActive ? "#06c755" : SEVERITY_STROKE[d.severity];
              const sw     = isActive ? 3 : 2;

              const bx = d.bbox_x * scaleX;
              const by = d.bbox_y * scaleY;
              const bw = d.bbox_w * scaleX;
              const bh = d.bbox_h * scaleY;

              const valLabel = showCurrentValue ? d.dev_value
                : showTargetValue ? d.design_value : null;

              const badgeX = Math.max(BADGE_R, bx);
              const badgeY = Math.max(BADGE_R, by);
              const fontSize = Math.max(10, vw * 0.024);

              return (
                <g key={d.id} style={{ pointerEvents: "all", cursor: "pointer" }}
                  onClick={() => onSelect(d.id)}>
                  {/* 영역 하이라이트 */}
                  <rect x={bx} y={by} width={bw} height={bh}
                    fill={fill} stroke={stroke} strokeWidth={sw} rx={4} />

                  {/* 값 레이블 */}
                  {valLabel && (
                    <g>
                      <rect
                        x={bx + bw / 2 - Math.max(valLabel.length * 4, 18)}
                        y={by + bh / 2 - fontSize * 0.7}
                        width={Math.max(valLabel.length * 8, 36)}
                        height={fontSize * 1.6}
                        rx={4} fill={stroke} opacity={0.88} />
                      <text x={bx + bw / 2} y={by + bh / 2 + fontSize * 0.35}
                        textAnchor="middle" fontSize={fontSize}
                        fontWeight={700} fill="white">
                        {valLabel}
                      </text>
                    </g>
                  )}

                  {/* 번호 배지 */}
                  <circle cx={badgeX - BADGE_R + 3} cy={badgeY - BADGE_R + 3}
                    r={BADGE_R}
                    fill={isApproved ? BADGE_APPROVED_BG : isActive ? BADGE_ACTIVE_BG : BADGE_BG}
                    stroke="white" strokeWidth={2} />
                  <text x={badgeX - BADGE_R + 3}
                    y={badgeY - BADGE_R + 3 + BADGE_R * 0.38}
                    textAnchor="middle" fontSize={BADGE_R * 0.9}
                    fontWeight={700} fill="white">
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
   OverlayView — 슬라이더 비교 모드
═══════════════════════════════════════════════════════════ */
function OverlayView({
  devUrl, designUrl, diffs, activeDiffId, onSelect,
  sliderX, onMouseMove, zoom, imageSize,
}: {
  devUrl: string; designUrl: string;
  diffs: Array<Difference & { num: number }>;
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
      <img ref={imgRef} src={devUrl} alt="beta" className="block max-w-full" draggable={false} />
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
          style={{ pointerEvents: "none" }}>
          {diffs.map((d) => {
            const isActive = activeDiffId === d.id;
            const badgeX = Math.max(BADGE_R, d.bbox_x);
            const badgeY = Math.max(BADGE_R, d.bbox_y);
            return (
              <g key={d.id} style={{ pointerEvents: "all", cursor: "pointer" }}
                onClick={() => onSelect(d.id)}>
                <rect x={d.bbox_x} y={d.bbox_y} width={d.bbox_w} height={d.bbox_h}
                  fill={isActive ? "rgba(6,199,85,0.18)" : "rgba(6,199,85,0.08)"}
                  stroke={isActive ? BADGE_ACTIVE_BG : BADGE_BG}
                  strokeWidth={isActive ? 3 : 2} rx={4} />
                <circle cx={badgeX - BADGE_R + 3} cy={badgeY - BADGE_R + 3} r={BADGE_R}
                  fill={isActive ? BADGE_ACTIVE_BG : BADGE_BG} stroke="white" strokeWidth={2} />
                <text x={badgeX - BADGE_R + 3} y={badgeY - BADGE_R + 3 + BADGE_R * 0.38}
                  textAnchor="middle" fontSize={BADGE_R * 0.9} fontWeight={700} fill="white">
                  {d.num}
                </text>
              </g>
            );
          })}
        </svg>
      )}

      <div className="absolute top-2 left-2 bg-line-50 text-line-700 text-xs px-2 py-0.5 rounded-full font-semibold pointer-events-none border border-line-200">Beta</div>
      <div className="absolute top-2 right-2 bg-surface-50 text-[#616161] text-xs px-2 py-0.5 rounded-full font-semibold pointer-events-none border border-surface-200">Design</div>
    </div>
  );
}
