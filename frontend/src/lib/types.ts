export type Severity = "critical" | "major" | "minor";
export type Category = "typography" | "color" | "spacing" | "layout" | "missing";
export type DiffStatus = "issue" | "approved" | "ignored";
export type AnalysisStatus = "pending" | "processing" | "done" | "failed";
export type InputMode = "screenshot" | "figma";
export type PipelineVersion = "v1_cv" | "v2_ai" | "v3_figma";

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
  design_bbox_x?: number;
  design_bbox_y?: number;
  design_bbox_w?: number;
  design_bbox_h?: number;
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
  pipeline_version?: PipelineVersion;
  input_mode?: InputMode;
  design_image: string;
  dev_image: string;
  marked_image: string | null;
  design_image_size?: ImageSize;
  dev_image_size?: ImageSize;
  summary: AnalysisSummary;
  differences: Difference[];
}
