# Demo akışı (portföy)

Bu doküman, projeyi **tarayıcıdan** veya **API ile** denemek içindir. Varsayılan API tabanı: `http://127.0.0.1:8000`. Örnek CSV’ler: `project/datasets/demo/`.

---

## A) Tarayıcı demo (önerilen — `project/frontend`)

Üstteki **1→9** şeridi, sırayı hatırlatır; her ekranda kısa **“Adım X / 9”** başlığı da vardır.

| Sıra | Ne olur | Kullanılan uçlar |
|-----|---------|------------------|
| 1 | CSV: **Ecommerce Churn Demo**, **Uplift Campaign Demo** veya kendi dosya | `POST /ingest/csv`, `POST /profile/{table_name}` |
| 2–4 | Önizleme; validation + quality; şablon: `churn` \| `uplift` \| … | `GET /preview/...`, `GET /datasets/{id}/validation?template=…`, `GET /datasets/{id}/quality?template=…` |
| 5–6 | Plan oluşturma (LLM + şema); içerik inceleme; **Planı onayla** | `POST /datasets/{id}/plans`, `POST /plans/{id}/approve` |
| 7–8 | **Job başlat**; durum polling; tamamlanınca sonuç | `POST /plans/{id}/jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/result` |
| 9 | Sonuç sayfasında metrikler; sağda **Explain** (otomatik + Yenile) | `POST /agent/explain` |

**Demo butonları:** `public/demo/ecommerce_good.csv` (churn) ve `public/demo/uplift_campaign_demo.csv` (uplift). Uplift demosunda şablon olarak **uplift** seçin; plan mock’u kampanya kolonlarıyla uyumlu yanıt üretebilir (`LLM_PROVIDER=mock`).

### Senaryo A — Churn Demo

1. **Ecommerce Churn Demo** → şablon `churn` (varsayılan) → plan `build_customer_rfm_features` → job → accuracy / churn_rate.

### Senaryo B — Uplift Campaign Demo

1. **Uplift Campaign Demo** → şablon **uplift** → validation/quality uplift kuralları → plan `build_uplift_customer_features` → job → uplift metrikleri (average_uplift, decile, hedef sayıları).

**Anahtarsız demo:** Backend `.env` içinde `LLM_PROVIDER=mock` — plan ve explain deterministik mock yanıtları kullanır (dış LLM çağrısı yok).

**Çalıştırma:** Backend ve frontend’i ayrı terminallerde açın; frontend’in backend’e gitmesi için `project/frontend/.env` veya `.env.local` içinde `VITE_API_URL` (bkz. `frontend/.env.example`). Ayrıntı: kök **[`README.md`](../README.md)**.

---

## B) Backend’i çalıştırma

```powershell
cd project\backend
# Sanal ortam (örnek)
.\myvenv\Scripts\Activate.ps1   # veya repo kökündeki myvenv
pip install -r requirements.txt
```

`project/backend/.env` içinde en azından `DATABASE_URL` ve tercihen `LLM_PROVIDER=mock` tanımlı olmalı (bkz. `backend/.env.example`).

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Sağlık:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/ready
```

---

## C) API ile uçtan uca (PowerShell)

### 1. CSV yükleme

`POST /ingest/csv` — form alanı: **`csv_file`**.

```powershell
$csv = "c:\path\to\project\datasets\demo\ecommerce_good.csv"
$uri = "http://127.0.0.1:8000/ingest/csv"
$r = Invoke-RestMethod -Uri $uri -Method Post -Form @{ csv_file = Get-Item -Path $csv }
$r | ConvertTo-Json
# dataset_id ve table_name not edin
```

### 2. Profil (plan için önkoşul)

```powershell
$tableName = "<ingest_yanıtındaki_table_name>"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/profile/$tableName" -Method Post
```

### 3. Validation ve quality

```powershell
$datasetId = 1
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/$datasetId/validation"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/$datasetId/quality"
# İsteğe bağlı: ?template=segmentasyon veya satis_tahmini
```

### 4. Plan oluşturma

```powershell
$body = @{ user_goal = "Churn riskini anlamak istiyorum" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/$datasetId/plans" -Method Post -Body $body -ContentType "application/json"
```

### 5. Plan onayı

```powershell
$planId = 1
Invoke-RestMethod -Uri "http://127.0.0.1:8000/plans/$planId/approve" -Method Post
```

### 6. Job ve sonuç

```powershell
$jobBody = @{ dataset_id = $datasetId } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/plans/$planId/jobs" -Method Post -Body $jobBody -ContentType "application/json"
$jobId = 1
Invoke-RestMethod -Uri "http://127.0.0.1:8000/jobs/$jobId"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/jobs/$jobId/result"
```

### 7. Explain

```powershell
$explainBody = @{ model_id = 1; user_goal = "Yöneticiye özetle" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/explain" -Method Post -Body $explainBody -ContentType "application/json"
```

---

## D) cURL (Linux / Git Bash)

```bash
export BASE=http://127.0.0.1:8000
curl -s "$BASE/health"
curl -s -X POST -F "csv_file=@project/datasets/demo/ecommerce_good.csv" "$BASE/ingest/csv"
curl -s -X POST "$BASE/profile/data_xxxxx"
curl -s "$BASE/datasets/1/validation"
curl -s -X POST "$BASE/datasets/1/plans" -H "Content-Type: application/json" -d '{"user_goal":"churn"}'
curl -s -X POST "$BASE/plans/1/approve"
curl -s -X POST "$BASE/plans/1/jobs" -H "Content-Type: application/json" -d '{"dataset_id":1}'
curl -s "$BASE/jobs/1"
curl -s "$BASE/jobs/1/result"
curl -s -X POST "$BASE/agent/explain" -H "Content-Type: application/json" -d '{"model_id":1}'
```

---

## E) Senkron alternatif: `POST /analyze`

Job kullanmak istemezseniz (ör. script veya eski istemci):

```powershell
$analyzeBody = @{ dataset_id = $datasetId; plan_id = $planId } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/analyze" -Method Post -Body $analyzeBody -ContentType "application/json"
```

Tarayıcı demosu varsayılan olarak **job akışını** kullanır.

---

## İlgili dokümanlar

- **[`API_EXAMPLES.md`](API_EXAMPLES.md)** — uç listesi ve örnekler  
- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — şablon mimarisi ve güvenlik  
- **[`DEPLOYMENT.md`](DEPLOYMENT.md)** — dağıtım seçenekleri  
