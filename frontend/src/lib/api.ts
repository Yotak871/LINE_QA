const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function startAnalysis(designFile: File, devFile: File) {
  const form = new FormData();
  form.append("design_image", designFile);
  form.append("dev_image", devFile);
  const res = await fetch(`${BASE}/api/analyze`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "업로드 실패");
  }
  return res.json() as Promise<{ analysis_id: string; status: string }>;
}

export async function getStatus(id: string) {
  const res = await fetch(`${BASE}/api/analyze/${id}/status`);
  if (!res.ok) throw new Error("상태 조회 실패");
  return res.json() as Promise<{ status: string; similarity_score: number | null; error_message: string | null }>;
}

export async function getResult(id: string) {
  const res = await fetch(`${BASE}/api/analyze/${id}/result`);
  if (!res.ok) throw new Error("결과 조회 실패");
  return res.json();
}

export async function updateDiffStatus(analysisId: string, diffId: string, status: string) {
  const res = await fetch(`${BASE}/api/analyze/${analysisId}/differences/${diffId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("상태 변경 실패");
  return res.json();
}

export async function createShareLink(analysisId: string, expiresDays: number | null) {
  const res = await fetch(`${BASE}/api/share/${analysisId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expires_days: expiresDays }),
  });
  if (!res.ok) throw new Error("링크 생성 실패");
  return res.json() as Promise<{ short_id: string; expires_at: string | null }>;
}

export function imageUrl(path: string) {
  if (path.startsWith("http")) return path;
  return `${BASE}${path}`;
}
