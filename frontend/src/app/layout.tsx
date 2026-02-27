import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DesignSync — AI Design QA",
  description: "디자인과 개발 화면을 AI로 자동 비교하세요",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen antialiased">
        <header className="border-b border-surface-100 bg-white px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* LINE logo icon */}
            <div className="w-8 h-8 rounded-lg bg-line-500 flex items-center justify-center shrink-0">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 1.5C4.86 1.5 1.5 4.36 1.5 7.875C1.5 10.995 4.095 13.59 7.755 14.145C7.755 14.145 7.5 14.865 7.41 15.3C7.275 15.87 7.635 16.005 8.025 15.765C8.34 15.57 11.055 13.725 12.285 12.72C14.01 11.4 15 9.735 15 7.875C15 4.36 12.165 1.5 9 1.5Z" fill="white"/>
              </svg>
            </div>
            <span className="font-seed font-black text-[#111] text-[16px] tracking-tight">LINE CREATIVE</span>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
