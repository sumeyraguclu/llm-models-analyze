import { useEffect, useState } from "react";

import { formatApiError } from "../api/errors";
import { getDatasetQuality, getDatasetValidation, getPreview } from "../api/client";
import type { QualityScoreResponse, ValidationReport } from "../types";
import { Button, Card, ProgressBar, Spinner } from "./ui";
import ChatPanel from "./ChatPanel";
import UpliftHelpText from "./UpliftHelpText";

const TEMPLATE_OPTIONS = [
  { value: "churn", label: "churn — müşteri kaybı (işlem satırları)" },
  { value: "uplift", label: "uplift — kampanya etkisi (müşteri/kampanya satırı)" },
  { value: "segmentasyon", label: "segmentasyon" },
  { value: "satis_tahmini", label: "satis_tahmini" },
] as const;

interface DatasetPageProps {
  datasetId: number;
  tableName: string;
  initialTemplate?: string;
  onStartAnalysis: () => void;
}

export default function DatasetPage({
  datasetId,
  tableName,
  initialTemplate = "churn",
  onStartAnalysis,
}: DatasetPageProps) {
  const [template, setTemplate] = useState<string>(initialTemplate);
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [vqLoading, setVqLoading] = useState(false);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [quality, setQuality] = useState<QualityScoreResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadPreview = async () => {
      setPreviewLoading(true);
      setError(null);
      try {
        const preview = await getPreview(tableName, 15);
        if (!cancelled) setRows(preview.rows);
      } catch (err) {
        if (!cancelled) setError(formatApiError(err, "Preview alınamadı."));
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    };
    loadPreview();
    return () => {
      cancelled = true;
    };
  }, [tableName]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setVqLoading(true);
      setError(null);
      try {
        const [vr, qr] = await Promise.all([
          getDatasetValidation(datasetId, template),
          getDatasetQuality(datasetId, template),
        ]);
        if (!cancelled) {
          setValidation(vr);
          setQuality(qr);
        }
      } catch (err) {
        if (!cancelled) setError(formatApiError(err, "Validation veya quality alınamadı."));
      } finally {
        if (!cancelled) setVqLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [datasetId, template]);

  const columns = rows[0] ? Object.keys(rows[0]) : [];
  const qualityLevelLabel =
    quality?.level === "good" ? "İyi" : quality?.level === "warning" ? "Uyarı" : quality?.level === "poor" ? "Zayıf" : "—";

  return (
    <div className="animate-fadeIn">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Adım 2–4 / 9 — Önizleme, validation, quality</p>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Dataset</h1>
          <p className="text-sm text-muted">
            <code className="text-xs">GET /preview/&#123;table_name&#125;</code> ·{" "}
            <code className="text-xs">GET /datasets/&#123;id&#125;/validation?template=…</code> ·{" "}
            <code className="text-xs">GET /datasets/&#123;id&#125;/quality?template=…</code>
          </p>
          <p className="mt-1 font-mono text-xs text-muted">dataset_id: {datasetId}</p>
          <p className="font-mono text-xs text-muted">table_name: {tableName}</p>
        </div>
        <Button variant="primary" onClick={onStartAnalysis}>
          5. Plan adımına geç →
        </Button>
      </div>

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted" htmlFor="demo-template">
          Şablon (validation / quality):
        </label>
        <select
          id="demo-template"
          className="rounded-lg border border-border bg-surface2 px-3 py-2 text-sm text-text"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        >
          {TEMPLATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {vqLoading && (
          <span className="flex items-center gap-2 text-xs text-muted">
            <Spinner size="sm" /> Validation/quality yenileniyor…
          </span>
        )}
      </div>

      {template === "uplift" && <UpliftHelpText className="mb-4" />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="text-lg font-semibold">2. Önizleme</h2>
          {previewLoading ? (
            <div className="mt-6 flex items-center gap-2 text-sm text-muted">
              <Spinner size="sm" /> Yükleniyor…
            </div>
          ) : (
            <>
              <p className="mt-1 text-sm text-muted">Kolonlar ({columns.length}): {columns.join(", ") || "—"}</p>
              <div className="mt-4 overflow-x-auto rounded-lg border border-border">
                <table className="w-full border-collapse text-sm">
                  <thead className="bg-surface2 text-muted">
                    <tr>
                      {columns.map((col) => (
                        <th key={col} className="border-b border-border px-3 py-2 text-left font-medium">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, idx) => (
                      <tr key={idx} className="odd:bg-black/10">
                        {columns.map((col) => (
                          <td key={`${idx}-${col}`} className="border-b border-border px-3 py-2">
                            {String(row[col] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">3–4. Validation &amp; quality</h2>
          {validation && (
            <p className="mt-2 text-sm">
              Geçerli:{" "}
              <span className={validation.is_valid ? "font-medium text-success" : "font-medium text-danger"}>
                {validation.is_valid ? "evet" : "hayır"}
              </span>
            </p>
          )}
          {quality && (
            <div className="mt-4 rounded-lg border border-border bg-surface2 p-4">
              <p className="text-xs text-muted">Kalite skoru</p>
              <div className="mt-1 flex flex-wrap items-end gap-3">
                <p className="text-3xl font-bold text-text">{quality.overall_score.toFixed(1)}</p>
                <span className="mb-1 rounded-md border border-border px-2 py-0.5 text-xs">{qualityLevelLabel}</span>
              </div>
              <div className="mt-3">
                <ProgressBar value={quality.overall_score} />
              </div>
              <p className="mt-2 text-xs text-muted">Alt bileşenler (0–100)</p>
              <ul className="mt-1 max-h-40 overflow-y-auto font-mono text-xs text-muted">
                {Object.entries(quality.breakdown)
                  .filter(([, v]) => v != null)
                  .map(([k, v]) => (
                    <li key={k}>
                      {k}: {typeof v === "number" ? v.toFixed(1) : String(v)}
                    </li>
                  ))}
              </ul>
            </div>
          )}
          {validation && (
            <div className="mt-4 space-y-3">
              {validation.errors.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase text-danger">Errors</p>
                  <ul className="mt-1 list-inside list-disc text-sm text-danger">
                    {validation.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}
              {validation.warnings.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase text-warning">Warnings</p>
                  <ul className="mt-1 list-inside list-disc text-sm text-muted">
                    {validation.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      <details className="mt-6 rounded-lg border border-border bg-surface2/50 p-4">
        <summary className="cursor-pointer text-sm font-medium text-text">İsteğe bağlı: agent sohbeti</summary>
        <div className="mt-4">
          <ChatPanel datasetId={datasetId} />
        </div>
      </details>
    </div>
  );
}
