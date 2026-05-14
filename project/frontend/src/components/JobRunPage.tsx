import axios from "axios";
import { useCallback, useState } from "react";

import { createAnalysisJob, formatApiError, getJobResult, getJobStatus } from "../api/client";
import type { AnalysisPlan, ModelMetrics } from "../types";
import { Badge, Button, Card, ProgressBar, Spinner } from "./ui";

const POLL_MS = 900;
const MAX_POLLS = 420;

interface JobRunPageProps {
  datasetId: number;
  planId: number;
  plan: AnalysisPlan;
  onComplete: (payload: {
    modelId: number;
    template: string;
    metrics: ModelMetrics;
    summary: string;
    dataWarning?: string | null;
  }) => void;
  onBackToStart: () => void;
}

type Phase = "idle" | "creating" | "polling" | "result_fetch" | "error";

export default function JobRunPage({ datasetId, planId, plan, onComplete, onBackToStart }: JobRunPageProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [jobId, setJobId] = useState<number | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const pollUntilDone = useCallback(
    async (jid: number) => {
      for (let i = 0; i < MAX_POLLS; i++) {
        const st = await getJobStatus(jid);
        setJobStatus(st.status);
        setJobProgress(st.progress);
        if (st.status === "completed") {
          return;
        }
        if (st.status === "failed") {
          throw new Error(st.error_message || "Job başarısız oldu.");
        }
        await new Promise((r) => setTimeout(r, POLL_MS));
      }
      throw new Error("Job zaman aşımı: durum izlemesi durduruldu.");
    },
    [],
  );

  const startJob = async () => {
    setError(null);
    setPhase("creating");
    try {
      const created = await createAnalysisJob(planId, datasetId);
      setJobId(created.job_id);
      setJobStatus(created.status);
      setJobProgress(0);
      setPhase("polling");
      await pollUntilDone(created.job_id);
      setPhase("result_fetch");
      try {
        const res = await getJobResult(created.job_id);
        onComplete({
          modelId: res.model_id,
          template: res.template,
          metrics: res.metrics,
          summary: res.summary ?? "",
          dataWarning: res.data_warning ?? null,
        });
      } catch (e) {
        if (axios.isAxiosError(e) && e.response?.status === 409) {
          setError(formatApiError(e, "Sonuç henüz hazır değil veya job başarısız."));
        } else {
          setError(formatApiError(e, "Sonuç alınamadı."));
        }
        setPhase("error");
      }
    } catch (e) {
      setError(formatApiError(e, "Job başlatılamadı veya çalışma sırasında hata oluştu."));
      setPhase("error");
    }
  };

  const busy = phase === "creating" || phase === "polling" || phase === "result_fetch";

  return (
    <div className="animate-fadeIn">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Adım 6–8 / 9 — Job &amp; sonuç</p>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Analiz job&apos;u</h1>
        <p className="mt-1 text-sm text-muted">
          API: <code className="text-xs">POST /plans/&#123;plan_id&#125;/jobs</code> →{" "}
          <code className="text-xs">GET /jobs/&#123;job_id&#125;</code> → <code className="text-xs">GET /jobs/&#123;job_id&#125;/result</code>
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-muted">Şablon</p>
            <Badge className="mt-1">{plan.template}</Badge>
            <p className="mt-3 text-sm text-muted">
              Plan ID: <span className="font-mono text-text">{planId}</span> · Dataset ID:{" "}
              <span className="font-mono text-text">{datasetId}</span>
            </p>
            {jobId != null && (
              <p className="mt-2 text-sm text-muted">
                Job ID: <span className="font-mono font-semibold text-accent">{jobId}</span>
              </p>
            )}
          </div>
          <Button variant="primary" onClick={startJob} disabled={busy || phase === "error"} loading={phase === "creating"}>
            {busy ? "Çalışıyor…" : "Job başlat (onaylı plan)"}
          </Button>
        </div>

        {busy && (
          <div className="mt-6 flex items-center gap-3 border-t border-border pt-6">
            <Spinner />
            <div>
              <p className="font-medium text-text">
                {phase === "creating"
                  ? "Job kuyruğa alınıyor…"
                  : phase === "result_fetch"
                    ? "Sonuçlar okunuyor…"
                    : "Model eğitimi çalışıyor…"}
              </p>
              <p className="text-sm text-muted">
                Durum: {jobStatus ?? "—"} {jobProgress != null ? `· İlerleme ${jobProgress}%` : ""}
              </p>
            </div>
          </div>
        )}

        {phase === "polling" && (
          <div className="mt-4">
            <p className="mb-2 text-xs text-muted">Adım 7 / 9 — Durum izleme (polling)</p>
            <ProgressBar value={Math.min(100, jobProgress)} />
          </div>
        )}
      </Card>

      {error && (
        <Card className="mt-4 border-danger/40">
          <p className="text-danger">{error}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => { setPhase("idle"); setError(null); }}>
              Yeniden dene
            </Button>
            <Button variant="ghost" onClick={onBackToStart}>
              Başa dön
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
