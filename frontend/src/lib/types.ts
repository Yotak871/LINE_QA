export type Severity = "critical" | "major" | "minor";
export type Category = "typography" | "color" | "spacing" | "layout" | "missing";
export type DiffStatus = "issue" | "approved" | "ignored";
export type AnalysisStatus = "pending" | "processing" | "done" | "failed";

export interface Difference {
  id: string;
  category: Category;
  severity: Severity;
  description: string;
  design_value: string;
  dev_value: string;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  status: DiffStatus;
}

export interface AnalysisSummary {
  critical: number;
  major: number;
  minor: number;
  approved: number;
  ignored: number;
}

export interface ImageSize {
  width: number;
  height: number;
}

export interface AnalysisResult {
  analysis_id: string;
  status: AnalysisStatus;
  similarity_score: number | null;
  design_image: string;
  dev_image: string;
  marked_image: string | null;
  design_image_size?: ImageSize;
  dev_image_size?: ImageSize;
  summary: AnalysisSummary;
  differences: Difference[];
}
