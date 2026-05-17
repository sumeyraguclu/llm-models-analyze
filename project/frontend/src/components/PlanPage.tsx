import { useEffect, useState } from "react";

import { approvePlanSnapshot, createPlanSnapshot, formatApiError } from "../api/client";
import type { AnalysisPlan } from "../types";
import { Badge, Button, Card, Divider, Skeleton, Spinner } from "./ui";

interface PlanPageProps {
  datasetId: number;
  tableName: string;
  userGoal?: string;
  onApprove: (planId: number, plan: AnalysisPlan) => void;
  onBack: () => void;
}

export default function PlanPage({ datasetId, tableName, userGoal, onApprove, onBack }: PlanPageProps) {
  const [planId, setPlanId] = useState<number | null>(null);
  const [plan, setPlan] = useState<AnalysisPlan | null>(null);
  const [mappingConfidence, setMappingConfidence] = useState<Record<string, unknown> | null>(null);
  const [snapshotWarnings, setSnapshotWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await createPlanSnapshot(datasetId, userGoal);
      setPlanId(res.plan_id);
      setPlan(res.plan);
      setMappingConfidence(res.mapping_confidence ?? null);
      setSnapshotWarnings(Array.isArray(res.warnings) ? res.warnings : []);
    } catch (err) {
      console.error(err);
      setError(formatApiError(err, "Plan oluşturulamadı. Profil adımını tamamlayıp tekrar deneyin."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  const handleApprove = async () => {
    if (planId == null || !plan) return;
    setApproving(true);
    setError(null);
    try {
      await approvePlanSnapshot(planId);
      onApprove(planId, plan);
    } catch (err) {
      console.error(err);
      setError(formatApiError(err, "Plan onaylanamadı. Bağlantıyı kontrol edip tekrar deneyin."));
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="animate-fadeIn">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Adım 5–6 / 9 — Plan &amp; onay</p>
      <div className="mb-6 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text">Analiz planı</h1>
          <p className="text-sm text-muted">
            <code className="text-xs">POST /datasets/&#123;id&#125;/plans</code> →{" "}
            <code className="text-xs">POST /plans/&#123;plan_id&#125;/approve</code>
          </p>
          <p className="text-sm text-muted">Dataset: {tableName}</p>
          {planId != null && <p className="mt-1 text-xs text-muted">Plan ID: {planId} (taslak)</p>}
        </div>
        <Button variant="ghost" onClick={onBack}>
          Geri
        </Button>
      </div>

      {loading && (
        <Card>
          <div className="flex items-center gap-3">
            <Spinner />
            <div>
              <p className="font-medium">Plan oluşturuluyor...</p>
              <p className="text-sm text-muted">LLM + kolon eşleştirme; taslak kaydediliyor.</p>
            </div>
          </div>
          <div className="mt-6 space-y-3">
            <Skeleton height={18} />
            <Skeleton height={18} />
            <Skeleton height={18} />
            <Skeleton height={18} />
          </div>
        </Card>
      )}

      {error && (
        <Card className="border-danger/40">
          <p className="text-danger">{error}</p>
          <div className="mt-4 flex gap-2">
            <Button variant="primary" onClick={load}>
              Tekrar Dene
            </Button>
          </div>
        </Card>
      )}

      {!loading && plan && (
        <div className="space-y-4">
          {(plan.template === "uplift" || plan.recommended_template === "uplift") && (
            <Card className="border-accent/30 bg-accent/5">
              <p className="text-sm text-text">
                <strong>Uplift</strong>, kampanya gönderilen ve gönderilmeyen grupları karşılaştırarak kampanyanın ek
                etkisini tahmin eder. Bu MVP customer-level campaign verisi içindir; causal inference iddiası yoktur.
              </p>
            </Card>
          )}

          <Card hover>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm text-muted">recommended_template / template</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Badge variant="default" className="text-sm">
                    {plan.recommended_template ?? plan.template}
                  </Badge>
                  {plan.recommended_template && plan.recommended_template !== plan.template && (
                    <Badge variant="default" className="text-sm">
                      normalize: {plan.template}
                    </Badge>
                  )}
                  {!plan.recommended_template && (
                    <span className="text-xs text-muted">(kaynak alan: template)</span>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {plan.confidence != null && (
                    <Badge variant="default" className="text-sm">
                      Güven: {plan.confidence}
                    </Badge>
                  )}
                  {plan.requires_user_confirmation && (
                    <Badge variant="warning" className="text-sm">
                      Onay önerilir
                    </Badge>
                  )}
                </div>
                {plan.reasoning && (
                  <p className="mt-2 text-xs italic text-muted">Gerekçe: {plan.reasoning}</p>
                )}
              </div>
              <Button variant="primary" onClick={handleApprove} disabled={approving || planId == null}>
                {approving ? "Onaylanıyor…" : "6. Planı onayla"}
              </Button>
            </div>
          </Card>

          {snapshotWarnings.length > 0 && (
            <Card className="border-accent/30">
              <h2 className="text-lg font-semibold">Plan snapshot uyarıları</h2>
              <p className="mt-1 text-xs text-muted">Sunucunun plan oluştururken eklediği uyarılar</p>
              <ul className="mt-2 list-inside list-disc text-sm text-muted">
                {snapshotWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Card>
          )}

          {plan.missing_required_columns && plan.missing_required_columns.length > 0 && (
            <Card className="border-warning/40">
              <h2 className="text-lg font-semibold text-warning">Eksik zorunlu alanlar</h2>
              <ul className="mt-2 list-inside list-disc text-sm text-text">
                {plan.missing_required_columns.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </Card>
          )}

          {plan.warnings && plan.warnings.length > 0 && (
            <Card className="border-warning/30">
              <h2 className="text-lg font-semibold">Uyarılar</h2>
              <ul className="mt-2 list-inside list-disc text-sm text-muted">
                {plan.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Card>
          )}

          {mappingConfidence && Object.keys(mappingConfidence).length > 0 && (
            <Card>
              <h2 className="text-lg font-semibold">Kolon eşleştirme güveni</h2>
              <p className="mt-1 text-xs text-muted">Backend hibrit eşleştirici (deterministik)</p>
              <Divider className="my-4" />
              <div className="space-y-2 text-xs font-mono text-muted">
                {Object.entries(mappingConfidence).map(([k, v]) => (
                  <div key={k} className="rounded border border-border bg-surface2 p-2">
                    <span className="font-semibold text-text">{k}</span>: {JSON.stringify(v)}
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <h2 className="text-lg font-semibold">Kolon eşleştirmesi</h2>
            <p className="mt-1 text-sm text-muted">Standart alan → CSV kolon adı</p>
            <Divider className="my-4" />

            <div className="overflow-hidden rounded-lg border border-border bg-surface2">
              <div className="grid grid-cols-3 gap-0 border-b border-border px-4 py-2 text-xs text-muted">
                <span>Standart</span>
                <span />
                <span>CSV kolonu</span>
              </div>
              {Object.entries(plan.column_map).map(([standard, original]) => (
                <div
                  key={`${standard}-${original}`}
                  className="grid grid-cols-3 gap-0 border-b border-border px-4 py-3 text-sm last:border-b-0"
                >
                  <span className="font-medium text-text">{standard}</span>
                  <span className="text-center text-muted">→</span>
                  <span className="text-text">{original}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold">cleaning_plan (cleaning_steps)</h2>
            <Divider className="my-4" />
            <ul className="space-y-2 text-sm">
              {(plan.cleaning_plan && plan.cleaning_plan.length > 0 ? plan.cleaning_plan : plan.cleaning_steps).map((step) => (
                <li key={step} className="text-text">
                  - <span className="text-muted">{step}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold">Özellik planı</h2>
            <Divider className="my-4" />
            <ul className="space-y-2 text-sm">
              {plan.feature_plan.map((f) => (
                <li key={f} className="text-text">
                  - <span className="text-muted">{f}</span>
                </li>
              ))}
            </ul>
          </Card>

          {plan.options &&
            (plan.template === "uplift" || plan.recommended_template === "uplift") &&
            !("churn_strategy" in plan.options) && (
              <Card>
                <h2 className="text-lg font-semibold">Uplift seçenekleri</h2>
                <Divider className="my-4" />
                <div className="space-y-2 text-sm text-text">
                  {"model_type" in plan.options && (
                    <p>
                      <span className="text-muted">model_type: </span>
                      {String((plan.options as Record<string, unknown>).model_type)}
                    </p>
                  )}
                  {"min_group_size" in plan.options && (
                    <p>
                      <span className="text-muted">min_group_size: </span>
                      {String((plan.options as Record<string, unknown>).min_group_size)}
                    </p>
                  )}
                  {"treatment_positive_value" in plan.options && (
                    <p>
                      <span className="text-muted">treatment_positive_value: </span>
                      {String((plan.options as Record<string, unknown>).treatment_positive_value)}
                    </p>
                  )}
                  {"outcome_positive_value" in plan.options && (
                    <p>
                      <span className="text-muted">outcome_positive_value: </span>
                      {String((plan.options as Record<string, unknown>).outcome_positive_value)}
                    </p>
                  )}
                </div>
              </Card>
            )}

          {plan.options && plan.template === "churn" && "churn_strategy" in plan.options && (
            <Card>
              <h2 className="text-lg font-semibold">Seçenekler</h2>
              <Divider className="my-4" />
              <div className="space-y-2 text-sm text-text">
                <p>
                  <span className="text-muted">Strateji: </span>
                  {plan.options.churn_strategy}
                </p>
                <p>
                  <span className="text-muted">Eşik: </span>
                  {plan.options.churn_threshold_days} gün
                </p>
                {plan.options.churn_strategy === "quantile" && (
                  <p>
                    <span className="text-muted">Quantile: </span>%{plan.options.churn_quantile * 100}
                  </p>
                )}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
