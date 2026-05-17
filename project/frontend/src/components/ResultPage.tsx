import { useCallback, useEffect, useState } from "react";

import { explainModel, formatApiError } from "../api/client";
import type { Explanation, ModelMetrics } from "../types";
import UpliftHelpText from "./UpliftHelpText";
import UpliftResultView from "./UpliftResultView";
import { Badge, Button, Card, Spinner } from "./ui";

interface ResultPageProps {
  modelId: number;
  template: string;
  metrics: ModelMetrics;
  /** Job sonucundan gelen kısa özet metni */
  summary?: string;
  /** GET /jobs/.../result üst düzey data_warning (varsa) */
  dataWarning?: string | null;
  onNewAnalysis: () => void;
}

function accuracyBadge(value: number) {
  const v = Number.isFinite(value) ? value : 0;
  if (v > 0.85) return <Badge variant="success">Yüksek</Badge>;
  if (v >= 0.7) return <Badge variant="warning">Orta</Badge>;
  return <Badge variant="danger">Düşük — daha fazla veri öneririz</Badge>;
}

function scoreBadge(value: number, kind: "higher_is_better" | "lower_is_better") {
  const v = Number.isFinite(value) ? value : 0;
  if (kind === "higher_is_better") {
    if (v > 0.8) return <Badge variant="success">İyi</Badge>;
    if (v > 0.6) return <Badge variant="warning">Orta</Badge>;
    return <Badge variant="danger">Zayıf</Badge>;
  }
  if (v < 0.3) return <Badge variant="success">İyi</Badge>;
  if (v < 1.0) return <Badge variant="warning">Orta</Badge>;
  return <Badge variant="danger">Zayıf</Badge>;
}

const METRIC_ENTRY_SKIP = new Set([
  "churn_rate",
  "accuracy",
  "train_size",
  "test_size",
  "treatment_conversion_rate",
  "control_conversion_rate",
  "average_uplift",
  "top_decile_uplift",
  "recommended_target_count",
  "do_not_target_count",
  "n_treatment",
  "n_control",
  "n_samples",
  "uplift_by_decile",
  "top_customers",
  "warnings",
  "feature_columns_used",
  "model_type",
  "uplift_score_min",
  "uplift_score_max",
  "low_priority_count",
]);

export default function ResultPage({
  modelId,
  template,
  metrics,
  summary = "",
  dataWarning: dataWarningProp = null,
  onNewAnalysis,
}: ResultPageProps) {
  const m = metrics as Record<string, unknown>;

  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [explainLoading, setExplainLoading] = useState(true);
  const [explainError, setExplainError] = useState<string | null>(null);

  const isUplift = template === "uplift";
  const upliftGoal =
    isUplift && typeof m.average_uplift === "number"
      ? `Uplift analizi: average_uplift=${m.average_uplift}, top_decile=${m.top_decile_uplift}, recommended_target=${m.recommended_target_count}`
      : undefined;

  const loadExplain = useCallback(async () => {
    setExplainLoading(true);
    setExplainError(null);
    try {
      const ex = await explainModel(modelId, upliftGoal);
      setExplanation(ex);
    } catch (err) {
      setExplanation(null);
      setExplainError(formatApiError(err, "Explain isteği başarısız."));
    } finally {
      setExplainLoading(false);
    }
  }, [modelId, upliftGoal]);

  useEffect(() => {
    void loadExplain();
  }, [loadExplain]);

  const dataWarningFromMetrics = typeof m["data_warning"] === "string" ? (m["data_warning"] as string) : null;
  const dataWarning = dataWarningProp || dataWarningFromMetrics;

  const churnRate = typeof m["churn_rate"] === "number" ? (m["churn_rate"] as number) : null;
  const accuracy = typeof m["accuracy"] === "number" ? (m["accuracy"] as number) : null;

  const featureImportances =
    typeof m["feature_importances"] === "object" && m["feature_importances"] !== null && !Array.isArray(m["feature_importances"])
      ? (m["feature_importances"] as Record<string, unknown>)
      : null;

  const baselines =
    typeof m["baselines"] === "object" && m["baselines"] !== null && !Array.isArray(m["baselines"])
      ? (m["baselines"] as Record<string, Record<string, unknown>>)
      : null;

  const metricWarnings = Array.isArray(m["metric_warnings"])
    ? (m["metric_warnings"] as unknown[]).filter((x): x is string => typeof x === "string")
    : [];

  const segmentDistribution =
    typeof m["segment_distribution"] === "object" && m["segment_distribution"] !== null && !Array.isArray(m["segment_distribution"])
      ? (m["segment_distribution"] as Record<string, unknown>)
      : null;

  const segmentActions =
    typeof m["segment_actions"] === "object" && m["segment_actions"] !== null && !Array.isArray(m["segment_actions"])
      ? (m["segment_actions"] as Record<string, unknown>)
      : null;

  const segments = (() => {
    if (!segmentDistribution) return null;
    const rows = Object.entries(segmentDistribution)
      .map(([name, v]) => [name, typeof v === "number" ? v : Number(v)] as const)
      .filter(([, v]) => Number.isFinite(v) && v > 0);
    if (rows.length === 0) return null;
    const total = rows.reduce((acc, [, v]) => acc + v, 0) || 1;
    return rows
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({
        name,
        count,
        pct: Math.round((count / total) * 100),
        total,
        action:
          segmentActions && typeof segmentActions[name] === "string" ? (segmentActions[name] as string) : null,
      }));
  })();

  const topFeatures = (() => {
    if (!featureImportances) return null;
    const entries = Object.entries(featureImportances)
      .map(([k, v]) => [k, typeof v === "number" ? v : Number(v)] as const)
      .filter(([, v]) => Number.isFinite(v));
    if (entries.length === 0) return null;
    const total = entries.reduce((acc, [, v]) => acc + Math.abs(v), 0) || 1;
    return entries
      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
      .slice(0, 8)
      .map(([name, v]) => ({ name, pct: Math.round((Math.abs(v) / total) * 100) }));
  })();

  const metricEntries = Object.entries(metrics ?? {})
    .filter(([k, v]) => typeof v === "number" && !METRIC_ENTRY_SKIP.has(k))
    .map(([k, v]) => [k, v as number]) as Array<[string, number]>;

  return (
    <div className="animate-slideUp">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Adım 8–9 / 9 — Sonuçlar &amp; Explain</p>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Sonuçlar</h1>
          <p className="text-sm text-muted">
            <code className="text-xs">GET /jobs/…/result</code> · <code className="text-xs">POST /agent/explain</code>
          </p>
          <p className="mt-1 text-sm text-muted">
            Model ID: <span className="font-mono text-text">{modelId}</span>
          </p>
        </div>
        <Badge>{template}</Badge>
      </div>

      {summary ? (
        <Card className="mb-4 border-border">
          <h2 className="text-sm font-semibold text-muted">Job özeti</h2>
          <p className="mt-2 text-sm text-text">{summary}</p>
        </Card>
      ) : null}

      {isUplift && <UpliftHelpText className="mb-4" />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:items-start">
        <div className="space-y-4">
          {isUplift && <UpliftResultView metrics={metrics} />}

          {!isUplift && segments && segments.length > 0 && (
            <Card>
              <h2 className="text-lg font-semibold">Segmentler ve önerilen aksiyonlar</h2>
              <p className="mt-1 text-sm text-muted">Hangi segmente ne yapmalıyım?</p>
              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                {segments.map((s) => {
                  const colorClass = s.name.includes("VIP")
                    ? "bg-white"
                    : s.name.includes("Sadık")
                      ? "bg-gray-200"
                      : s.name.includes("Büyük")
                        ? "bg-gray-400"
                        : "bg-gray-600";
                  return (
                    <div key={s.name} className="rounded-xl border border-border bg-surface2 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-text">{s.name}</p>
                          <p className="mt-0.5 text-xs text-muted">
                            {s.count} müşteri • %{s.pct}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-border">
                        <div className={`h-full ${colorClass}`} style={{ width: `${(s.count / s.total) * 100}%` }} />
                      </div>
                      {s.action && <p className="mt-3 text-sm text-muted">{s.action}</p>}
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {dataWarning && (
            <Card className="border-yellow-500/30 bg-surface2">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 text-warning">⚠</div>
                <div>
                  <p className="text-sm font-medium text-text">Veri uyarısı</p>
                  <p className="mt-1 text-sm text-text">{dataWarning}</p>
                </div>
              </div>
            </Card>
          )}

          {metricWarnings.length > 0 && (
            <Card className="border-warning/40">
              <h2 className="text-lg font-semibold">Metrik uyarıları</h2>
              <ul className="mt-2 list-inside list-disc text-sm text-muted">
                {metricWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Card>
          )}

          {!isUplift && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {accuracy !== null && (
              <Card hover>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs text-muted">accuracy</p>
                    <p className="mt-1 text-2xl font-bold text-text">{accuracy.toFixed(4)}</p>
                  </div>
                  {accuracyBadge(accuracy)}
                </div>
              </Card>
            )}

            {churnRate !== null && (
              <Card hover>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs text-muted">churn_rate</p>
                    <p className="mt-1 text-2xl font-bold text-text">%{Math.round(churnRate * 100)} churn riski</p>
                  </div>
                  <Badge variant="default">Oran</Badge>
                </div>
              </Card>
            )}

            {metricEntries.map(([name, value]) => {
              const lowerIsBetter = name.toLowerCase().includes("rmse") || name.toLowerCase().includes("mae");
              const kind = lowerIsBetter ? "lower_is_better" : "higher_is_better";
              return (
                <Card key={name} hover>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted">{name}</p>
                      <p className="mt-1 text-2xl font-bold text-text">{value.toFixed(4)}</p>
                    </div>
                    {scoreBadge(value, kind)}
                  </div>
                </Card>
              );
            })}
          </div>
          )}

          {!isUplift && baselines && Object.keys(baselines).length > 0 && (
            <Card>
              <h2 className="text-lg font-semibold">Baseline metrikleri</h2>
              <p className="mt-1 text-xs text-muted">Kural tabanlı kıyaslar (ör. majority class)</p>
              <div className="mt-4 space-y-3">
                {Object.entries(baselines).map(([name, obj]) => (
                  <div key={name} className="rounded-lg border border-border bg-surface2 p-3 font-mono text-xs">
                    <p className="font-semibold text-text">{name}</p>
                    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-muted">{JSON.stringify(obj, null, 2)}</pre>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {!isUplift && topFeatures && topFeatures.length > 0 && (
            <Card>
              <h2 className="text-lg font-semibold">Özellik önemi (feature importance)</h2>
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-text">
                {topFeatures.map((f, idx) => (
                  <li key={`${f.name}-${idx}`}>
                    {f.name} <span className="text-muted">(%{f.pct})</span>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </div>

        <Card className="border-accent/30 lg:sticky lg:top-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">9. Explain (LLM)</h2>
            <Button variant="ghost" size="sm" onClick={() => void loadExplain()} disabled={explainLoading}>
              Yenile
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted">Mock provider ile de çalışır; ağ hatası burada görünür.</p>

          {explainLoading && (
            <div className="mt-6 flex items-center gap-2 text-sm text-muted">
              <Spinner size="sm" /> Açıklama yükleniyor…
            </div>
          )}

          {explainError && <p className="mt-4 text-sm text-danger">{explainError}</p>}

          {!explainLoading && explanation && (
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-base font-semibold leading-snug text-text">{explanation.summary}</p>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-muted">Temel bulgular</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-text">
                  {explanation.key_findings.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-muted">Önerilen aksiyonlar</h3>
                <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-text">
                  {explanation.recommended_actions.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ol>
              </div>
              {explanation.caveats.length > 0 && (
                <div className="rounded-lg border border-warning/40 p-3">
                  <h3 className="text-sm font-semibold text-warning">Dikkat</h3>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-text">
                    {explanation.caveats.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      <div className="pt-6">
        <Button variant="ghost" onClick={onNewAnalysis}>
          Yeni analiz (başa dön)
        </Button>
      </div>
    </div>
  );
}
