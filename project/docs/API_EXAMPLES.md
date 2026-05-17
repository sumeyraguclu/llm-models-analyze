# API örnekleri (gerçek uçlar)

Taban URL örnek: `http://127.0.0.1:8000`. Aşağıdaki yollar `project/backend/main.py` ve `project/backend/routers/*.py` ile uyumludur.

---

## 1. Dataset yükleme (CSV)

**`POST /ingest/csv`** — multipart, alan adı: `csv_file`.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest/csv" -Method Post `
  -Form @{ csv_file = Get-Item "c:\Users\Sumeyra\dev\aProject\project\datasets\demo\ecommerce_good.csv" }
```

```bash
curl -s -X POST -F "csv_file=@project/datasets/demo/ecommerce_good.csv" http://127.0.0.1:8000/ingest/csv
```

---

## 2. Profil (plan / agent önkoşulu)

**`POST /profile/{table_name}`** — `ingest` yanıtındaki `table_name`.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/profile/data_ab12cd34" -Method Post
```

---

## 3. Validation

**`GET /datasets/{dataset_id}/validation`**

İsteğe bağlı query: **`template`** — `churn` (varsayılan) \| `segmentasyon` \| `satis_tahmini` \| **`uplift`**.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/validation"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/validation?template=segmentasyon"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest/csv" -Method Post `
  -Form @{ csv_file = Get-Item "project\datasets\demo\uplift_campaign_demo.csv" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/validation?template=uplift"
```

---

## 4. Quality

**`GET /datasets/{dataset_id}/quality`**

Aynı **`template`** query parametresi (varsayılan `churn`).

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/quality"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/quality?template=satis_tahmini"
```

---

## 5. Plan oluşturma (LLM + doğrulama)

**`POST /datasets/{dataset_id}/plans`** — JSON gövde: `user_goal` isteğe bağlı.

```powershell
$body = '{"user_goal":"Churn analizi"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/plans" -Method Post -Body $body -ContentType "application/json"
```

---

## 6. Plan listesi

**`GET /datasets/{dataset_id}/plans`**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1/plans"
```

---

## 7. Plan detayı (snapshot)

**`GET /plans/{plan_id}`**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/plans/1"
```

---

## 8. Plan onayı

**`POST /plans/{plan_id}/approve`**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/plans/1/approve" -Method Post
```

İlgili (isteğe bağlı): **`POST /plans/{plan_id}/reject`** (yalnızca `draft`).

---

## 9. Analiz job oluşturma

**`POST /plans/{plan_id}/jobs`** — JSON: `{"dataset_id": <int>}` (planın `dataset_id` ile aynı olmalı).

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/plans/1/jobs" -Method Post `
  -Body '{"dataset_id":1}' -ContentType "application/json"
```

---

## 10. Job durumu

**`GET /jobs/{job_id}`**

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/jobs/1"
```

---

## 11. Job sonucu

**`GET /jobs/{job_id}/result`** — `status == completed` iken anlamlı; aksi halde 409.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/jobs/1/result"
```

---

## 12. Explain

**`POST /agent/explain`** — JSON: `model_id` (zorunlu), `user_goal` (isteğe bağlı).

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/explain" -Method Post `
  -Body '{"model_id":1,"user_goal":"Özetle"}' -ContentType "application/json"
```

---

## 13. Senkron analiz (legacy / UI)

**`POST /analyze`** — Örnek: onaylı plan ile.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/analyze" -Method Post `
  -Body '{"dataset_id":1,"plan_id":1}' -ContentType "application/json"
```

Alternatif gövdeler: tam `analysis_plan` veya `template` + `column_map` (bkz. `routers/analyze.py`).

---

## 14. Önizleme ve dataset listesi (preview router)

| Metod | Yol |
|--------|-----|
| GET | `/preview/{table_name}` — query: `limit` (1–200, varsayılan 20) |
| GET | `/datasets` |
| GET | `/datasets/{dataset_id}` |

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/preview/data_ab12cd34?limit=10"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/datasets/1"
```

---

## 15. Sağlık

| Metod | Yol |
|--------|-----|
| GET | `/health` |
| GET | `/ready` |

---

## Diğer agent uçları (referans)

| Metod | Yol |
|--------|-----|
| POST | `/agent/chat` |
| POST | `/agent/analysis-plan` |

---

## Uplift MVP notu

- Plan: `template: "uplift"`, `feature_plan: ["build_uplift_customer_features"]`, `column_map`: customer_id, treatment, outcome (+ opsiyonel RFM/channel).
- Job/analyze uplift planı ile **T-Learner** eğitir; metrikler: `average_uplift`, `uplift_by_decile`, `recommended_target_count`, vb.
- **Sınırlar:** customer-level campaign CSV; transaction-level uplift yok; causal inference iddiası yok.

## TODO

- OpenAPI şemasından tam request/response alan listesi otomatik üretilebilir (`/docs` Swagger UI).
