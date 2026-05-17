import { useState } from "react";

import { createProfile, ingestCsv, type IngestResponse, type ProfileResponse } from "../api/client";
import { formatApiError } from "../api/errors";
import { Button, Card, Spinner } from "./ui";

export type DemoScenario = "churn" | "uplift";

interface UploadPageProps {
  onReady: (data: {
    ingest: IngestResponse;
    profile: ProfileResponse["profile"];
    demoScenario?: DemoScenario;
  }) => void;
}

const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024;
const DEMO_CHURN_URL = "/demo/ecommerce_good.csv";
const DEMO_UPLIFT_URL = "/demo/uplift_campaign_demo.csv";

export default function UploadPage({ onReady }: UploadPageProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ingestDone, setIngestDone] = useState<IngestResponse | null>(null);
  const [profilePayload, setProfilePayload] = useState<ProfileResponse["profile"] | null>(null);
  const [lastDemo, setLastDemo] = useState<DemoScenario | null>(null);

  const runIngestAndProfile = async (csvFile: File, demoScenario?: DemoScenario) => {
    if (csvFile.size > MAX_FILE_SIZE_BYTES) {
      setError("Dosya 100MB sınırını aşıyor.");
      return;
    }
    setLoading(true);
    setError(null);
    setIngestDone(null);
    setProfilePayload(null);
    setLastDemo(demoScenario ?? null);
    try {
      const ingest = await ingestCsv(csvFile);
      const profile = await createProfile(ingest.table_name);
      setIngestDone(ingest);
      setProfilePayload(profile.profile);
    } catch (err) {
      setError(formatApiError(err, "Yükleme veya profil oluşturma sırasında hata oluştu."));
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Lütfen bir CSV dosyası seç.");
      return;
    }
    await runIngestAndProfile(file);
    setLastDemo(null);
  };

  const loadDemo = async (url: string, filename: string, scenario: DemoScenario) => {
    setError(null);
    setFile(null);
    setLoading(true);
    try {
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`Demo dosyası yüklenemedi (${res.status}). public/demo/${filename} var mı?`);
      }
      const blob = await res.blob();
      const demoFile = new File([blob], filename, { type: "text/csv" });
      setFile(demoFile);
      await runIngestAndProfile(demoFile, scenario);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo CSV alınamadı.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = () => {
    if (ingestDone && profilePayload != null) {
      onReady({ ingest: ingestDone, profile: profilePayload, demoScenario: lastDemo ?? undefined });
    }
  };

  return (
    <div className="animate-fadeIn">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Adım 1 / 9 — CSV yükleme</p>
      <div className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">E‑ticaret CSV → doğrulama, plan, job, ML sonuç</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
          İki portföy demosu: <strong className="text-text">Churn</strong> (işlem satırları) veya{" "}
          <strong className="text-text">Uplift</strong> (kampanya müşteri satırları). Üstteki 1→9 sırasını izleyin.
        </p>
        <p className="mt-2 text-xs text-muted">
          API: <code>POST /ingest/csv</code> → <code>POST /profile/&#123;table_name&#125;</code>
        </p>
      </div>

      <Card className="mx-auto max-w-xl">
        <h2 className="text-xl font-semibold">1. Dataset yükle</h2>
        <p className="mt-1 text-sm text-muted">Demo seçin veya kendi CSV’nizi yükleyin. Maks. 100MB.</p>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button
            type="button"
            variant="ghost"
            onClick={() => loadDemo(DEMO_CHURN_URL, "ecommerce_good.csv", "churn")}
            disabled={loading}
          >
            Ecommerce Churn Demo
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => loadDemo(DEMO_UPLIFT_URL, "uplift_campaign_demo.csv", "uplift")}
            disabled={loading}
          >
            Uplift Campaign Demo
          </Button>
        </div>

        <div className="mt-4">
          <input
            type="file"
            accept=".csv,text/csv"
            className="block w-full cursor-pointer rounded-lg border border-border bg-surface2 px-3 py-2 text-sm text-text file:mr-3 file:rounded-md file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-black hover:border-accentDim"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setIngestDone(null);
              setProfilePayload(null);
              setLastDemo(null);
            }}
          />
        </div>

        <div className="mt-4 flex items-center justify-between gap-3">
          <Button onClick={handleUpload} loading={loading} disabled={!file}>
            Yükle ve profille
          </Button>
          {loading && (
            <div className="flex items-center gap-2 text-sm text-muted">
              <Spinner size="sm" />
              <span>İşleniyor…</span>
            </div>
          )}
        </div>

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}

        {ingestDone && profilePayload != null && (
          <div className="mt-6 rounded-lg border border-success/30 bg-success/5 p-4">
            <p className="text-sm font-medium text-text">Yükleme tamam</p>
            {lastDemo && (
              <p className="mt-1 text-xs text-muted">
                Demo senaryo: <strong className="text-text">{lastDemo === "uplift" ? "Uplift Campaign" : "Churn"}</strong>
                {lastDemo === "uplift" && " — sonraki adımda şablon olarak uplift seçin."}
              </p>
            )}
            <ul className="mt-2 space-y-1 font-mono text-xs text-muted">
              <li>
                <span className="text-text">dataset_id:</span> {ingestDone.dataset_id}
              </li>
              <li>
                <span className="text-text">table_name:</span> {ingestDone.table_name}
              </li>
              <li>
                <span className="text-text">row_count:</span> {ingestDone.row_count} ·{" "}
                <span className="text-text">column_count:</span> {ingestDone.column_count}
              </li>
            </ul>
            <Button className="mt-4" variant="primary" onClick={handleContinue}>
              2. Önizleme ve doğrulamaya geç →
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}