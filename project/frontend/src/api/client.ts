import axios from "axios";

import type {
  AnalysisPlan,
  AnalyzeResponse,
  CreateJobResponse,
  CreatePlanResponse,
  Explanation,
  JobResultResponse,
  JobStatusResponse,
  PlanListItem,
  PreviewData,
  QualityScoreResponse,
  ValidationReport,
} from "../types";

export { formatApiError } from "./errors";

export interface IngestResponse {
  dataset_id: number;
  table_name: string;
  row_count: number;
  column_count: number;
}

export interface ProfileResponse {
  dataset_id: number;
  table_name: string;
  profile: Record<string, unknown>;
}

export interface PreviewResponse {
  table_name: string;
  limit: number;
  rows: Array<Record<string, unknown>>;
}

export interface AgentChatResponse {
  reply: string;
}

export interface AnalysisPlanResponse {
  analysis_plan: AnalysisPlan;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});

export async function ingestCsv(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("csv_file", file);
  const response = await api.post<IngestResponse>("/ingest/csv", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function createProfile(tableName: string): Promise<ProfileResponse> {
  const response = await api.post<ProfileResponse>(`/profile/${tableName}`);
  return response.data;
}

export async function getPreview(tableName: string, limit = 20): Promise<PreviewResponse> {
  const response = await api.get<PreviewResponse>(`/preview/${tableName}`, { params: { limit } });
  return response.data;
}

/** GET /datasets/{id}/validation — `template`: churn | uplift | segmentasyon | satis_tahmini (varsayılan churn). */
export async function getDatasetValidation(datasetId: number, template = "churn"): Promise<ValidationReport> {
  const response = await api.get<ValidationReport>(`/datasets/${datasetId}/validation`, {
    params: { template },
  });
  return response.data;
}

/** GET /datasets/{id}/quality */
export async function getDatasetQuality(datasetId: number, template = "churn"): Promise<QualityScoreResponse> {
  const response = await api.get<QualityScoreResponse>(`/datasets/${datasetId}/quality`, {
    params: { template },
  });
  return response.data;
}

export async function chatWithAgent(datasetId: number, message: string): Promise<AgentChatResponse> {
  const response = await api.post<AgentChatResponse>("/agent/chat", {
    dataset_id: datasetId,
    message,
  });
  return response.data;
}

export async function getAnalysisPlan(datasetId: number, userGoal?: string): Promise<AnalysisPlan> {
  const response = await api.post<AnalysisPlanResponse>("/agent/analysis-plan", {
    dataset_id: datasetId,
    user_goal: userGoal,
  });
  return response.data.analysis_plan;
}

/** Önerilen akış: plan snapshot oluştur (draft), incele, sonra approve. */
export async function createPlanSnapshot(datasetId: number, userGoal?: string): Promise<CreatePlanResponse> {
  const response = await api.post<CreatePlanResponse>(`/datasets/${datasetId}/plans`, {
    user_goal: userGoal ?? null,
  });
  return response.data;
}

export async function listPlanSnapshots(datasetId: number): Promise<{ dataset_id: number; plans: PlanListItem[] }> {
  const response = await api.get<{ dataset_id: number; plans: PlanListItem[] }>(`/datasets/${datasetId}/plans`);
  return response.data;
}

export async function getPlanSnapshot(planId: number): Promise<{
  id: number;
  dataset_id: number;
  status: string;
  source: string;
  created_at: string | null;
  approved_at: string | null;
  plan: AnalysisPlan;
  mapping_confidence: Record<string, unknown> | null;
  warnings: string[];
}> {
  const response = await api.get(`/plans/${planId}`);
  return response.data;
}

export async function approvePlanSnapshot(planId: number): Promise<{ plan_id: number; status: string; approved_at: string | null }> {
  const response = await api.post(`/plans/${planId}/approve`);
  return response.data;
}

/** POST /plans/{plan_id}/jobs — yalnızca onaylı plan; gövde: { dataset_id }. */
export async function createAnalysisJob(planId: number, datasetId: number): Promise<CreateJobResponse> {
  const response = await api.post<CreateJobResponse>(`/plans/${planId}/jobs`, { dataset_id: datasetId });
  return response.data;
}

export async function getJobStatus(jobId: number): Promise<JobStatusResponse> {
  const response = await api.get<JobStatusResponse>(`/jobs/${jobId}`);
  return response.data;
}

/** Tamamlanan job için sonuç; 409 = henüz hazır değil veya failed. */
export async function getJobResult(jobId: number): Promise<JobResultResponse> {
  const response = await api.get<JobResultResponse>(`/jobs/${jobId}/result`);
  return response.data;
}

export async function analyzeDataset(payload: {
  dataset_id: number;
  template?: string;
  analysis_plan?: AnalysisPlan;
  plan_id?: number;
}): Promise<AnalyzeResponse> {
  const body: Record<string, unknown> = { dataset_id: payload.dataset_id };
  if (payload.plan_id != null) {
    body.plan_id = payload.plan_id;
    if (payload.template) body.template = payload.template;
  } else {
    if (!payload.analysis_plan) {
      throw new Error("analysis_plan veya plan_id gerekli.");
    }
    body.template = payload.template ?? payload.analysis_plan.template;
    body.analysis_plan = payload.analysis_plan;
  }
  const response = await api.post<AnalyzeResponse>("/analyze", body);
  return response.data;
}

export async function explainModel(modelId: number, userGoal?: string): Promise<Explanation> {
  const response = await api.post<Explanation>("/agent/explain", {
    model_id: modelId,
    user_goal: userGoal,
  });
  return response.data;
}

export type { PreviewData };
