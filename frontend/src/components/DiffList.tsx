"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import clsx from "clsx";
import type { Difference, DiffStatus } from "@/lib/types";

const CATEGORY_LABEL: Record<string, string> = {
  typography: "Typography",
  color:      "Color",
  spacing:    "Spacing",
  layout:     "Layout",
  missing:    "Missing",
};

/* 심각도 색상 */
const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-[#e02000]",
  major:    "bg-orange-500",
  minor:    "bg-yellow-500",
};

interface Props {
  differences:  Difference[];
  activeDiffId: string | null;
  onSelect:     (id: string) => void;
  onStatusChange: (diffId: string, status: DiffStatus) => void;
}

type Filter = "all" | "issue" | "approved" | "ignored";

export default function DiffList({ differences, activeDiffId, onSelect, onStatusChange }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  const counts: Record<Filter, number> = {
    all:      differences.length,
    issue:    differences.filter(d => d.status === "issue").length,
    approved: differences.filter(d => d.status === "approved").length,
    ignored:  differences.filter(d => d.status === "ignored").length,
  };

  /* 번호는 전체 목록 순서 기준 (ignored 포함 전체에서 index) */
  const withIndex = differences.map((d, i) => ({ ...d, num: i + 1 }));
  const filtered  = withIndex.filter(d => filter === "all" || d.status === filter);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 필터 탭 */}
      <div className="flex gap-1 px-3 py-2.5 border-b border-surface-100 bg-surface-50 shrink-0">
        {(["all", "issue", "approved", "ignored"] as Filter[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              "flex-1 py-1 text-xs font-medium rounded-md transition-colors",
              filter === f
                ? "bg-white text-[#111] shadow-sm border border-surface-100"
                : "text-[#999] hover:text-[#616161]"
            )}
          >
            {f === "all" ? "전체" : f === "issue" ? "미해결" : f === "approved" ? "승인" : "무시"}
            <span className="ml-1 text-[#b7b7b7] font-normal">({counts[f]})</span>
          </button>
        ))}
      </div>

      {/* 목록 */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-sm text-[#b7b7b7]">항목이 없습니다</div>
        ) : (
          <div className="divide-y divide-surface-100">
            {filtered.map(diff => (
              <DiffItem
                key={diff.id}
                diff={diff}
                isActive={activeDiffId === diff.id}
                onSelect={() => onSelect(diff.id)}
                onStatusChange={s => onStatusChange(diff.id, s)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────── */

function DiffItem({
  diff,
  isActive,
  onSelect,
  onStatusChange,
}: {
  diff: Difference & { num: number };
  isActive: boolean;
  onSelect: () => void;
  onStatusChange: (s: DiffStatus) => void;
}) {
  const [open, setOpen] = useState(false);

  const isIgnored  = diff.status === "ignored";
  const isApproved = diff.status === "approved";

  return (
    <div
      className={clsx(
        "px-3 py-3 cursor-pointer transition-colors",
        isActive
          ? "bg-line-50 border-l-2 border-line-500"
          : "hover:bg-surface-50 border-l-2 border-transparent",
        isIgnored && "opacity-50"
      )}
      onClick={onSelect}
    >
      <div className="flex items-start gap-2.5">
        {/* 번호 배지 — LINE green 원 */}
        <div className={clsx(
          "shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white mt-0.5",
          isApproved ? "bg-line-500" : isIgnored ? "bg-[#b7b7b7]" : isActive ? "bg-[#e02000]" : "bg-line-500"
        )}>
          {diff.num}
        </div>

        <div className="flex-1 min-w-0">
          {/* 카테고리 + 심각도 점 */}
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="text-sm font-bold text-[#111]">
              {CATEGORY_LABEL[diff.category] ?? diff.category}
            </span>
            <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", SEVERITY_DOT[diff.severity])} />
            <span className="text-xs text-[#999] capitalize">{diff.severity}</span>
          </div>

          {/* 설명 */}
          <p className="text-xs text-[#616161] leading-relaxed line-clamp-3">
            {diff.description}
          </p>

          {/* 수치 비교: Design값 → Dev값 */}
          {(diff.design_value || diff.dev_value) && (
            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
              {diff.design_value && (
                <span className="text-xs bg-surface-50 text-[#616161] border border-surface-100 px-1.5 py-0.5 rounded font-mono">
                  {diff.design_value}
                </span>
              )}
              {diff.design_value && diff.dev_value && (
                <span className="text-[#b7b7b7] text-xs">→</span>
              )}
              {diff.dev_value && (
                <span className="text-xs bg-red-50 text-[#e02000] border border-red-100 px-1.5 py-0.5 rounded font-mono">
                  {diff.dev_value}
                </span>
              )}
            </div>
          )}
        </div>

        {/* 펼치기 버튼 */}
        <button
          className="text-[#b7b7b7] hover:text-[#616161] mt-0.5 shrink-0"
          onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
        >
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* 액션 버튼 (펼쳤을 때) */}
      {open && (
        <div
          className="mt-2 ml-8 flex gap-2"
          onClick={e => e.stopPropagation()}
        >
          {diff.status !== "approved" && (
            <ActionBtn
              onClick={() => onStatusChange("approved")}
              className="text-line-700 border-line-200 hover:bg-line-50"
            >
              ✓ 승인
            </ActionBtn>
          )}
          {diff.status !== "ignored" && (
            <ActionBtn
              onClick={() => onStatusChange("ignored")}
              className="text-[#616161] border-surface-200 hover:bg-surface-50"
            >
              무시
            </ActionBtn>
          )}
          {diff.status !== "issue" && (
            <ActionBtn
              onClick={() => onStatusChange("issue")}
              className="text-[#e02000] border-red-200 hover:bg-red-50"
            >
              미해결로 되돌리기
            </ActionBtn>
          )}
        </div>
      )}
    </div>
  );
}

function ActionBtn({
  children, onClick, className,
}: {
  children: React.ReactNode;
  onClick: () => void;
  className: string;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "text-xs px-2.5 py-1 rounded-md border transition-colors font-medium",
        className
      )}
    >
      {children}
    </button>
  );
}
