"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";
import UploadZone from "@/components/UploadZone";
import { startAnalysis } from "@/lib/api";

/* ─── 타이핑 모션 히어로 ─────────────────────────────────── */
const HERO_LINES = [
  { text: "With LINE Design Sync,", highlight: false },
  { text: "LINER communicates in", highlight: false },
  { text: "one unified design eyes.", highlight: true },
];

function TypingHero() {
  const [lineIdx, setLineIdx] = useState(0);
  const [charIdx, setCharIdx] = useState(0);
  const [done, setDone] = useState(false);

  const tick = useCallback(() => {
    if (lineIdx >= HERO_LINES.length) { setDone(true); return; }
    const currentLine = HERO_LINES[lineIdx].text;
    if (charIdx < currentLine.length) {
      setCharIdx((c) => c + 1);
    } else {
      setTimeout(() => { setLineIdx((l) => l + 1); setCharIdx(0); }, 280);
    }
  }, [lineIdx, charIdx]);

  useEffect(() => {
    if (done) return;
    if (lineIdx >= HERO_LINES.length) { setDone(true); return; }
    const currentLine = HERO_LINES[lineIdx].text;
    if (charIdx < currentLine.length) {
      const timer = setTimeout(tick, charIdx === 0 ? 80 : 32);
      return () => clearTimeout(timer);
    } else {
      const timer = setTimeout(() => { setLineIdx((l) => l + 1); setCharIdx(0); }, 320);
      return () => clearTimeout(timer);
    }
  }, [lineIdx, charIdx, done, tick]);

  return (
    <h1
      className="font-seed text-[#111] leading-[1.10] tracking-[-0.02em] text-center"
      style={{ fontSize: "clamp(32px, 5vw, 60px)" }}
    >
      {HERO_LINES.map((line, li) => {
        const isCurrentLine = li === lineIdx;
        const isPastLine = li < lineIdx || done;
        const visibleChars = isPastLine ? line.text.length : isCurrentLine ? charIdx : 0;
        return (
          <span key={li} className="block" style={{ minHeight: "1.15em" }}>
            {line.highlight ? (
              <span className="font-black text-line-500">{line.text.slice(0, visibleChars)}</span>
            ) : (
              <span className="font-black">{line.text.slice(0, visibleChars)}</span>
            )}
            {isCurrentLine && !done && (
              <span
                className="inline-block w-[3px] bg-line-500 ml-0.5 rounded-sm animate-pulse"
                style={{ height: "0.85em", verticalAlign: "baseline", marginBottom: "-0.08em" }}
              />
            )}
          </span>
        );
      })}
    </h1>
  );
}

/* ─── 메인 페이지 ─────────────────────────────────────────── */
export default function HomePage() {
  const router = useRouter();
  const [designFile, setDesignFile] = useState<File | null>(null);
  const [devFile, setDevFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canAnalyze = designFile && devFile && !loading;

  const handleAnalyze = async () => {
    if (!designFile || !devFile) return;
    setLoading(true);
    setError(null);
    try {
      const { analysis_id } = await startAnalysis(designFile, devFile);
      router.push(`/result/${analysis_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류가 발생했습니다.");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-16 sm:py-20">
      {/* Hero */}
      <div className="mb-14 sm:mb-16">
        <TypingHero />
      </div>

      {/* 업로드 카드 */}
      <div className="bg-white rounded-xl border border-surface-100 p-6 sm:p-8 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 sm:gap-8">
          <UploadZone
            label="디자인 원본"
            hint="Figma Export 또는 디자인 캡처본"
            file={designFile}
            onFile={setDesignFile}
            onClear={() => setDesignFile(null)}
          />
          <UploadZone
            label="개발 화면"
            hint="배포된 화면의 스크린샷"
            file={devFile}
            onFile={setDevFile}
            onClear={() => setDevFile(null)}
          />
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mt-8 flex justify-center">
          <button
            onClick={handleAnalyze}
            disabled={!canAnalyze}
            className="flex items-center gap-2 bg-[#e5e5e5] text-[#999] hover:bg-line-500 hover:text-white disabled:cursor-not-allowed font-semibold px-10 py-3.5 rounded-lg transition-all text-[15px] hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 [&:not(:disabled)]:bg-line-500 [&:not(:disabled)]:text-white [&:not(:disabled)]:hover:bg-line-600"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                분석 요청 중...
              </>
            ) : (
              <>
                AI 분석 시작
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </div>

        {(!designFile || !devFile) && (
          <p className="text-center text-xs text-[#b7b7b7] mt-4">
            디자인 원본과 개발 화면을 모두 올려주세요
          </p>
        )}
      </div>

    </div>
  );
}
