"use client";

/**
 * 데모 페이지 — 실제 API 없이 결과 화면 미리보기
 * http://localhost:3000/demo
 */

import { useState, useCallback } from "react";
import { Share2, CheckCircle } from "lucide-react";
import ImageViewer from "@/components/ImageViewer";
import DiffList from "@/components/DiffList";
import type { AnalysisResult, DiffStatus } from "@/lib/types";

/* ─── Mock 데이터 (참조 이미지 기반) ─────────────────────── */
const MOCK: AnalysisResult = {
  analysis_id: "demo",
  status: "done",
  similarity_score: 73.4,
  design_image: "/demo-design.png",
  dev_image:    "/demo-beta.png",
  marked_image: null,
  summary: { critical: 1, major: 3, minor: 1, approved: 0, ignored: 0 },
  differences: [
    {
      id: "d1",
      category: "spacing",
      severity: "major",
      description: "일러스트와 타이틀 사이 간격을 24px로 수정해야 합니다.",
      design_value: "24px",
      dev_value: "20px",
      bbox_x: 40,  bbox_y: 280, bbox_w: 300, bbox_h: 28,
      status: "issue",
    },
    {
      id: "d2",
      category: "spacing",
      severity: "major",
      description: "섹션 타이틀과 콘텐츠 사이 간격, 콘텐츠 간 간격을 12px로 수정해야 합니다.",
      design_value: "12px",
      dev_value: "14px / 16px",
      bbox_x: 40, bbox_y: 360, bbox_w: 300, bbox_h: 120,
      status: "issue",
    },
    {
      id: "d3",
      category: "spacing",
      severity: "major",
      description: "면책조항 텍스트와 CTA 버튼 사이 간격을 16px로 수정해야 합니다.",
      design_value: "16px",
      dev_value: "12px",
      bbox_x: 40, bbox_y: 500, bbox_w: 300, bbox_h: 36,
      status: "issue",
    },
    {
      id: "d4",
      category: "layout",
      severity: "critical",
      description: "버튼 너비가 343px이어야 합니다. 좌우 여백 16px 기준으로 맞춰주세요.",
      design_value: "343px",
      dev_value: "전체 폭",
      bbox_x: 20, bbox_y: 545, bbox_w: 340, bbox_h: 48,
      status: "issue",
    },
    {
      id: "d5",
      category: "spacing",
      severity: "minor",
      description: "좌우 여백 16px, CTA 하단 여백 34px (모바일 클리어링과 동일)로 맞춰주세요.",
      design_value: "16px / 34px",
      dev_value: "20px / 20px",
      bbox_x: 0, bbox_y: 545, bbox_w: 20, bbox_h: 100,
      status: "issue",
    },
  ],
};

/* 데모용 플레이스홀더 이미지 (SVG base64) */
const DESIGN_PLACEHOLDER = `data:image/svg+xml;utf8,${encodeURIComponent(`
<svg width="390" height="680" xmlns="http://www.w3.org/2000/svg">
  <rect width="390" height="680" fill="#f8fafc"/>
  <!-- 상태바 -->
  <rect width="390" height="48" fill="#1e293b"/>
  <text x="195" y="30" text-anchor="middle" fill="white" font-size="14" font-family="sans-serif">9:41</text>
  <!-- 일러스트 영역 -->
  <rect x="120" y="80" width="150" height="180" rx="12" fill="#e2e8f0"/>
  <text x="195" y="178" text-anchor="middle" fill="#94a3b8" font-size="13" font-family="sans-serif">Illustration</text>
  <!-- 24px gap marker -->
  <rect x="80" y="260" width="230" height="24" fill="#fce7f3" opacity="0.7"/>
  <text x="195" y="276" text-anchor="middle" fill="#db2777" font-size="11" font-weight="bold" font-family="sans-serif">24px</text>
  <!-- 타이틀 -->
  <text x="195" y="316" text-anchor="middle" fill="#0f172a" font-size="20" font-weight="bold" font-family="sans-serif">Get started with LINE</text>
  <text x="195" y="340" text-anchor="middle" fill="#0f172a" font-size="20" font-weight="bold" font-family="sans-serif">SHOPPING</text>
  <!-- 설명 텍스트 -->
  <text x="195" y="368" text-anchor="middle" fill="#64748b" font-size="12" font-family="sans-serif">By clicking Continue, you have read and</text>
  <text x="195" y="386" text-anchor="middle" fill="#64748b" font-size="12" font-family="sans-serif">agree LINE SHOPPING terms &amp; conditions</text>
  <!-- 12px gap marker -->
  <rect x="80" y="398" width="230" height="12" fill="#fce7f3" opacity="0.7"/>
  <text x="195" y="408" text-anchor="middle" fill="#db2777" font-size="10" font-weight="bold" font-family="sans-serif">12px</text>
  <!-- 토글 섹션 -->
  <rect x="16" y="416" width="358" height="50" rx="8" fill="#f1f5f9"/>
  <text x="32" y="446" fill="#334155" font-size="12" font-family="sans-serif">Add friend with LINE SHOPPING OA</text>
  <rect x="330" y="428" width="36" height="20" rx="10" fill="#06c755"/>
  <!-- 12px gap -->
  <rect x="80" y="466" width="230" height="12" fill="#fce7f3" opacity="0.7"/>
  <text x="195" y="476" text-anchor="middle" fill="#db2777" font-size="10" font-weight="bold" font-family="sans-serif">12px</text>
  <rect x="16" y="478" width="358" height="50" rx="8" fill="#f1f5f9"/>
  <text x="32" y="508" fill="#334155" font-size="12" font-family="sans-serif">Allow using personal data for analysis</text>
  <rect x="330" y="490" width="36" height="20" rx="10" fill="#06c755"/>
  <!-- disclaimer -->
  <text x="195" y="546" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="sans-serif">If you would like to manage the use...</text>
  <!-- 16px gap -->
  <rect x="80" y="554" width="230" height="16" fill="#fce7f3" opacity="0.7"/>
  <text x="195" y="566" text-anchor="middle" fill="#db2777" font-size="10" font-weight="bold" font-family="sans-serif">16px</text>
  <!-- CTA 버튼 (343px, 16px 좌우 여백) -->
  <rect x="24" y="572" width="342" height="48" rx="12" fill="#06c755"/>
  <text x="195" y="602" text-anchor="middle" fill="white" font-size="16" font-weight="bold" font-family="sans-serif">Continue</text>
  <!-- 16px / 34px 여백 표시 -->
  <rect x="0" y="572" width="16" height="80" fill="#fce7f3" opacity="0.7"/>
  <rect x="374" y="572" width="16" height="80" fill="#fce7f3" opacity="0.7"/>
  <!-- 34px 하단 여백 -->
  <rect x="80" y="620" width="230" height="34" fill="#fce7f3" opacity="0.7"/>
  <text x="195" y="641" text-anchor="middle" fill="#db2777" font-size="10" font-weight="bold" font-family="sans-serif">34px</text>
  <!-- 홈 인디케이터 -->
  <rect x="155" y="658" width="80" height="4" rx="2" fill="#334155"/>
  <text x="195" y="20" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="sans-serif">Design</text>
</svg>
`)}`;

const BETA_PLACEHOLDER = `data:image/svg+xml;utf8,${encodeURIComponent(`
<svg width="390" height="680" xmlns="http://www.w3.org/2000/svg">
  <rect width="390" height="680" fill="#f8fafc"/>
  <!-- 상태바 (회색 - beta) -->
  <rect width="390" height="48" fill="#475569"/>
  <text x="195" y="30" text-anchor="middle" fill="white" font-size="14" font-family="sans-serif">Beta Build</text>
  <!-- 일러스트 영역 -->
  <rect x="120" y="80" width="150" height="180" rx="12" fill="#e2e8f0"/>
  <text x="195" y="178" text-anchor="middle" fill="#94a3b8" font-size="13" font-family="sans-serif">Illustration</text>
  <!-- 20px gap (틀림) -->
  <rect x="80" y="260" width="230" height="20" fill="#fee2e2" opacity="0.7"/>
  <text x="195" y="273" text-anchor="middle" fill="#dc2626" font-size="11" font-weight="bold" font-family="sans-serif">20px ← 틀림</text>
  <!-- 타이틀 (태국어) -->
  <text x="195" y="312" text-anchor="middle" fill="#0f172a" font-size="18" font-weight="bold" font-family="sans-serif">เริ่มช้อปกับ LINE SHOPPING</text>
  <!-- 설명 텍스트 -->
  <text x="195" y="342" text-anchor="middle" fill="#64748b" font-size="12" font-family="sans-serif">โดยการกดปุ่ม "ต่อไป" คุณได้อ่าน</text>
  <text x="195" y="360" text-anchor="middle" fill="#3b82f6" font-size="12" font-family="sans-serif">ข้อกำหนดและเงื่อนไขการใช้บริการ</text>
  <!-- 14px gap (틀림) -->
  <rect x="80" y="372" width="230" height="14" fill="#fee2e2" opacity="0.7"/>
  <text x="195" y="383" text-anchor="middle" fill="#dc2626" font-size="10" font-weight="bold" font-family="sans-serif">14px ← 틀림</text>
  <!-- 토글 섹션 -->
  <rect x="16" y="390" width="358" height="50" rx="8" fill="#f1f5f9"/>
  <text x="32" y="420" fill="#334155" font-size="12" font-family="sans-serif">เพิ่ม LINE SHOPPING Official Account</text>
  <rect x="330" y="402" width="36" height="20" rx="10" fill="#06c755"/>
  <!-- 16px gap (틀림) -->
  <rect x="80" y="440" width="230" height="16" fill="#fee2e2" opacity="0.7"/>
  <text x="195" y="452" text-anchor="middle" fill="#dc2626" font-size="10" font-weight="bold" font-family="sans-serif">16px ← 틀림</text>
  <rect x="16" y="456" width="358" height="50" rx="8" fill="#f1f5f9"/>
  <text x="32" y="486" fill="#334155" font-size="12" font-family="sans-serif">อนุญาตให้ใช้ข้อมูลส่วนตัว</text>
  <rect x="330" y="468" width="36" height="20" rx="10" fill="#06c755"/>
  <!-- disclaimer -->
  <text x="195" y="522" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="sans-serif">คุณสามารถจัดการสิทธิ์การใช้ข้อมูล...</text>
  <!-- 12px gap (틀림) -->
  <rect x="80" y="528" width="230" height="12" fill="#fee2e2" opacity="0.7"/>
  <text x="195" y="538" text-anchor="middle" fill="#dc2626" font-size="10" font-weight="bold" font-family="sans-serif">12px ← 틀림</text>
  <!-- CTA 버튼 (전체 폭, 좌우 20px 여백 — 틀림) -->
  <rect x="20" y="545" width="350" height="48" rx="8" fill="#06c755"/>
  <text x="195" y="575" text-anchor="middle" fill="white" font-size="16" font-weight="bold" font-family="sans-serif">ต่อไป</text>
  <!-- 20px / 20px 여백 (틀림) -->
  <rect x="0" y="545" width="20" height="88" fill="#fee2e2" opacity="0.7"/>
  <rect x="370" y="545" width="20" height="88" fill="#fee2e2" opacity="0.7"/>
  <!-- 20px 하단 여백 (틀림) -->
  <rect x="80" y="593" width="230" height="20" fill="#fee2e2" opacity="0.7"/>
  <text x="195" y="607" text-anchor="middle" fill="#dc2626" font-size="10" font-weight="bold" font-family="sans-serif">20px ← 틀림</text>
  <!-- 홈 인디케이터 -->
  <rect x="155" y="638" width="80" height="4" rx="2" fill="#334155"/>
  <text x="195" y="20" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="sans-serif">Beta (개발)</text>
</svg>
`)}`;

export default function DemoPage() {
  const [data, setData] = useState<AnalysisResult>({
    ...MOCK,
    design_image: DESIGN_PLACEHOLDER,
    dev_image:    BETA_PLACEHOLDER,
  });
  const [activeDiffId, setActiveDiffId] = useState<string | null>(null);
  const [shareMsg, setShareMsg] = useState<string | null>(null);

  const handleStatusChange = useCallback((diffId: string, status: DiffStatus) => {
    setData(prev => ({
      ...prev,
      differences: prev.differences.map(d => d.id === diffId ? { ...d, status } : d),
    }));
  }, []);

  const { summary, differences, similarity_score } = data;

  return (
    <div className="flex flex-col h-[calc(100vh-57px)]">
      {/* 상단 바 */}
      <div className="bg-white border-b border-surface-100 px-6 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          {/* 데모 배지 */}
          <span className="text-xs bg-line-50 text-line-700 border border-line-200 px-2.5 py-1 rounded-full font-medium">
            Demo 미리보기
          </span>

          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-[#616161]">유사도</span>
            <span className={`text-sm font-bold ${
              (similarity_score ?? 0) >= 90 ? "text-line-500" :
              (similarity_score ?? 0) >= 70 ? "text-orange-500" : "text-[#e02000]"
            }`}>
              {similarity_score?.toFixed(1)}%
            </span>
          </div>

          <div className="h-4 w-px bg-surface-100" />

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
            onClick={() => { setShareMsg("데모 링크가 복사됐습니다!"); setTimeout(() => setShareMsg(null), 2500); }}
            className="flex items-center gap-1.5 text-sm px-4 py-2 border border-surface-100 rounded-lg hover:bg-surface-50 transition-colors text-[#616161]"
          >
            <Share2 size={14} />
            공유 링크
          </button>
          <a href="/" className="text-sm px-4 py-2 bg-line-500 hover:bg-line-600 text-white rounded-lg transition-colors font-medium">
            새 분석
          </a>
        </div>
      </div>

      {/* 메인: 이미지 뷰어 + 수정사항 패널 */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-hidden p-4">
          <ImageViewer
            designUrl={data.design_image}
            devUrl={data.dev_image}
            differences={differences}
            activeDiffId={activeDiffId}
            onSelectDiff={setActiveDiffId}
            devImageSize={{ width: 390, height: 680 }}
            designImageSize={{ width: 390, height: 680 }}
          />
        </div>

        {/* 수정사항 패널 */}
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
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#e02000] inline-block"/>Critical</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500 inline-block"/>Major</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500 inline-block"/>Minor</span>
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
