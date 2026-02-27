"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { Loader2, AlertTriangle, Share2, CheckCircle } from "lucide-react";
import { getStatus, getResult, updateDiffStatus, createShareLink, imageUrl } from "@/lib/api";
import type { AnalysisResult, Difference, DiffStatus } from "@/lib/types";
import ImageViewer from "@/components/ImageViewer";
import DiffList from "@/components/DiffList";

const STATUS_STEPS = ["pending", "processing", "done"];
const STEP_LABELS = ["이미지 전처리", "픽셀 비교", "AI 분석"];

export default function ResultPage() {
  const { id } = useParams<{ id: string }>();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [pollingStatus, setPollingStatus] = useState<string>("pending");
  const [error, setError] = useState<string | null>(null);
  const [activeDiffId, setActiveDiffId] = useState<string | null>(null);
  const [shareMsg, setShareMsg] = useState<string | null>(null);

  // 분석 완료까지 폴링
  useEffect(() => {
    if (!id) return;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const s = await getStatus(id);
        setPollingStatus(s.status);
        if (s.status === "done") {
          const r = await getResult(id);
          setResult(r);
        } else if (s.status === "failed") {
          setError(s.error_message ?? "분석에 실패했습니다.");
        } else {
          timer = setTimeout(poll, 2000);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "조회 실패");
      }
    };

    poll();
    return () => clearTimeout(timer);
  }, [id]);

  const handleStatusChange = useCallback(async (diffId: string, status: DiffStatus) => {
    if (!id || !result) return;
    await updateDiffStatus(id, diffId, status);
    setResult((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        differences: prev.differences.map((d) =>
          d.id === diffId ? { ...d, status } : d
        ),
      };
    });
  }, [id, result]);

  const handleShare = async () => {
    if (!id) return;
    try {
      const { short_id } = await createShareLink(id, 30);
      const url = `${window.location.origin}/share/${short_id}`;
      await navigator.clipboard.writeText(url);
      setShareMsg("링크가 복사됐습니다! (30일 유효)");
      setTimeout(() => setShareMsg(null), 3000);
    } catch {
      setShareMsg("링크 생성에 실패했습니다.");
    }
  };

  // ── 분석 중 로딩 화면 ──────────────────────────────────────
  if (!result && !error) {
    const stepIdx = STATUS_STEPS.indexOf(pollingStatus);

    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-57px)] bg-surface-50">
        <div className="bg-white rounded-xl border border-surface-100 p-10 max-w-sm w-full mx-4">
          {/* 스피너 */}
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-full bg-line-50 flex items-center justify-center">
              <Loader2 size={32} className="animate-spin text-line-500" />
            </div>
          </div>

          {/* 텍스트 */}
          <h2 className="text-center font-bold text-[#111] text-lg mb-1">
            AI가 분석 중입니다
          </h2>
          <p className="text-center text-[#999] text-sm mb-8">
            최대 30초 소요됩니다
          </p>

          {/* 진행 단계 */}
          <div className="space-y-3">
            {STEP_LABELS.map((label, i) => {
              const done    = i < stepIdx;
              const active  = i === stepIdx;
              const pending = i > stepIdx;
              return (
                <div key={label} className="flex items-center gap-3">
                  <div className={`
                    w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors
                    ${done    ? "bg-line-500"           : ""}
                    ${active  ? "bg-line-50 border-2 border-line-500" : ""}
                    ${pending ? "bg-surface-50 border-2 border-surface-200" : ""}
                  `}>
                    {done ? (
                      <CheckCircle size={14} className="text-white" />
                    ) : active ? (
                      <div className="w-2 h-2 rounded-full bg-line-500 animate-pulse" />
                    ) : (
                      <div className="w-2 h-2 rounded-full bg-[#ccc]" />
                    )}
                  </div>
                  <span className={`text-sm font-medium transition-colors ${
                    done || active ? "text-[#111]" : "text-[#999]"
                  }`}>
                    {label}
                  </span>
                  {done && (
                    <span className="ml-auto text-xs text-line-500 font-medium">완료</span>
                  )}
                  {active && (
                    <span className="ml-auto text-xs text-line-500 font-medium animate-pulse">진행 중…</span>
                  )}
                </div>
              );
            })}
          </div>

          <p className="text-center text-xs text-[#ccc] mt-8 font-mono">{id}</p>
        </div>
      </div>
    );
  }

  // ── 에러 화면 ──────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-57px)] bg-surface-50">
        <div className="bg-white rounded-xl border border-surface-100 p-10 max-w-sm w-full mx-4 text-center">
          <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-5">
            <AlertTriangle size={28} className="text-[#e02000]" />
          </div>
          <h2 className="font-bold text-[#111] text-lg mb-2">분석에 실패했습니다</h2>
          <p className="text-sm text-[#616161] mb-6 leading-relaxed">{error}</p>
          <a
            href="/"
            className="inline-block text-sm px-5 py-2.5 bg-line-500 hover:bg-line-600 text-white rounded-lg transition-colors font-medium"
          >
            처음으로 돌아가기
          </a>
        </div>
      </div>
    );
  }

  if (!result) return null;

  const { summary, differences, similarity_score } = result;

  return (
    <div className="flex flex-col h-[calc(100vh-57px)]">
      {/* ── 상단 요약 바 ─────────────────────────────────────── */}
      <div className="bg-white border-b border-surface-100 px-6 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          {/* 유사도 */}
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-[#616161]">유사도</span>
            <span className={`text-sm font-bold ${
              (similarity_score ?? 0) >= 90 ? "text-line-500" :
              (similarity_score ?? 0) >= 70 ? "text-orange-500" : "text-[#e02000]"
            }`}>
              {similarity_score?.toFixed(1) ?? "—"}%
            </span>
          </div>

          <div className="h-4 w-px bg-surface-100" />

          {/* 심각도 카운트 */}
          <div className="flex items-center gap-3 text-sm">
            <span className="flex items-center gap-1.5">
              <span className="w-5 h-5 rounded-full bg-[#e02000] flex items-center justify-center text-white text-xs font-bold">
                {summary.critical}
              </span>
              <span className="text-[#616161]">Critical</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-5 h-5 rounded-full bg-orange-500 flex items-center justify-center text-white text-xs font-bold">
                {summary.major}
              </span>
              <span className="text-[#616161]">Major</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-5 h-5 rounded-full bg-yellow-500 flex items-center justify-center text-white text-xs font-bold">
                {summary.minor}
              </span>
              <span className="text-[#616161]">Minor</span>
            </span>
            {summary.approved > 0 && (
              <span className="flex items-center gap-1.5">
                <CheckCircle size={14} className="text-line-500" />
                <span className="text-[#616161]">{summary.approved} 승인됨</span>
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {shareMsg && (
            <span className="text-xs text-line-600 bg-line-50 border border-line-100 px-3 py-1.5 rounded-lg">
              {shareMsg}
            </span>
          )}
          <button
            onClick={handleShare}
            className="flex items-center gap-1.5 text-sm px-4 py-2 border border-surface-100 rounded-lg hover:bg-surface-50 transition-colors text-[#616161]"
          >
            <Share2 size={14} />
            공유 링크 복사
          </button>
          <a
            href="/"
            className="text-sm px-4 py-2 bg-line-500 hover:bg-line-600 text-white rounded-lg transition-colors font-medium"
          >
            새 분석
          </a>
        </div>
      </div>

      {/* ── 메인 레이아웃: 이미지 뷰어 + 사이드 패널 ─────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* 이미지 뷰어 */}
        <div className="flex-1 overflow-hidden p-4">
          <ImageViewer
            designUrl={imageUrl(result.design_image)}
            devUrl={imageUrl(result.dev_image)}
            differences={differences}
            activeDiffId={activeDiffId}
            onSelectDiff={setActiveDiffId}
            devImageSize={result.dev_image_size}
            designImageSize={result.design_image_size}
          />
        </div>

        {/* 수정사항 사이드 패널 */}
        <div className="w-96 border-l border-surface-100 bg-white flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-surface-100">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-[#111]">수정 사항</h2>
                <p className="text-xs text-[#999] mt-0.5">
                  {differences.filter(d => d.status === "issue").length}개 미해결 · {differences.length}개 전체
                </p>
              </div>
              <div className="flex items-center gap-2 text-xs text-[#999]">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-[#e02000] inline-block" />Critical
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-orange-500 inline-block" />Major
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block" />Minor
                </span>
              </div>
            </div>
          </div>
          <DiffList
            differences={differences}
            activeDiffId={activeDiffId}
            onSelect={setActiveDiffId}
            onStatusChange={handleStatusChange}
          />
        </div>
      </div>
    </div>
  );
}
