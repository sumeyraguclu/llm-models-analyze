export interface ChurnOptions {
  churn_strategy: "fixed_days" | "quantile";
  churn_threshold_days: number;
  churn_quantile: number;
}

export interface UpliftOptions {
  treatment_positive_value?: number;
  outcome_positive_value?: number;
  min_group_size?: number;
  min_outcome_rate?: number;
  model_type?: "t_learner" | "two_model_uplift";
}

export interface AnalysisPlan {
  /** Normalize edilmiş şablon; LLM ham çıktısında `recommended_template` de gelebilir. */
  template: string; // "churn" | "uplift" | "satis_tahmini" | "segmentasyon"
  recommended_template?: string;
  column_map: Record<string, string>; // standart alan adı → CSV kolon adı
  cleaning_steps: string[];
  /** Bazı yanıtlarda `cleaning_plan` adıyla gelebilir; UI `cleaning_steps` ile birleştirir. */
  cleaning_plan?: string[];
  feature_plan: string[];
  options?: ChurnOptions | UpliftOptions;
  reasoning?: string;
  /** @deprecated Sunucu artık insufficient_data ile plan döndürmez; uyumluluk için bırakıldı. */
  insufficient_data?: boolean;
  message?: string;
  suggestion?: string;
  confidence?: number;
  requires_user_confirmation?: boolean;
  missing_required_columns?: string[];
  warnings?: string[];
  dataset_type?: string | null;
}

/** POST /datasets/{id}/plans yanıtı */
export interface CreatePlanResponse {
  plan_id: number;
  dataset_id: number;
  status: string;
  source: string;
  created_at: string | null;
  plan: AnalysisPlan;
  mapping_confidence: Record<string, unknown>;
  warnings: string[];
}

export interface PlanListItem {
  plan_id: number;
  dataset_id: number;
  status: string;
  source: string;
  template: string | null;
  created_at: string | null;
  approved_at: string | null;
}

export type ModelMetrics = Record<string, unknown>;

export interface AnalyzeResponse {
  model_id: number;
  template: string;
  metrics: ModelMetrics;
  summary: string;
  data_warning?: string | null;
}

export interface ValidationReport {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  metrics: Record<string, unknown>;
  resolved_columns: Record<string, string | null>;
}

export interface QualityScoreResponse {
  overall_score: number;
  level: "good" | "warning" | "poor";
  breakdown: Record<string, number>;
  weights: Record<string, number>;
}

export interface CreateJobResponse {
  job_id: number;
  dataset_id: number;
  plan_snapshot_id: number;
  status: string;
}

export interface JobStatusResponse {
  job_id: number;
  dataset_id: number;
  plan_snapshot_id: number;
  status: string;
  progress: number;
  result_model_run_id: number | null;
  error_message: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobResultResponse {
  model_id: number;
  template: string;
  metrics: ModelMetrics;
  summary: string;
  data_warning?: string | null;
}

export interface Explanation {
  summary: string;
  key_findings: string[];
  recommended_actions: string[];
  caveats: string[];
}

export interface Dataset {
  id: number;
  file_name: string;
  table_name: string;
  column_defs: unknown;
  column_profile: unknown;
  created_at?: string;
}

export interface PreviewData {
  table_name: string;
  limit: number;
  rows: Array<Record<string, unknown>>;
}
