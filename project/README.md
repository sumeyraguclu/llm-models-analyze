# AutoML Agent — Portfolio

E‑ticaret işlem CSV’lerinden **kolon eşleştirme**, **veri doğrulama**, **LLM destekli analysis plan**, **onaylı plan ile güvenli feature pipeline** ve **şablon kayıtlı (template-driven) ML** üreten tam yığın demo. Şablonlar: **churn**, **segmentasyon**, **satış tahmini** (`project/backend/templates/`).

| Bileşen | Konum |
|---------|--------|
| Backend (FastAPI) | `project/backend/` |
| Frontend (Vite + React + demo akışı) | `project/frontend/` |
| Demo CSV (repo) | `project/datasets/demo/` + `project/frontend/public/demo/` (UI “Demo CSV” butonu) |
| Dokümantasyon | `project/docs/` |

---

## Canlı demo (Vercel + Render + Neon)

Adım adım rehber: **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)**. Özet: Neon `DATABASE_URL` → Render (FastAPI, `LLM_PROVIDER=mock`, `CORS_ORIGINS`) → Vercel (`VITE_API_URL` = Render URL, Root = `project/frontend`). Blueprint dosyası repo yapınıza göre **`render.yaml`** (repo kökü `aProject`) veya **`project/render.yaml`** (repo kökü yalnız `project/`).

---

## Hızlı başlangıç (backend + frontend)

### 1) Ortam dosyaları

- **Backend:** `project/backend/.env.example` → kopyalayın `.env` yapın; en azından `DATABASE_URL` ve portföy için `LLM_PROVIDER=mock`.
- **Frontend:** `project/frontend/.env.example` → `.env` veya `.env.local`; `VITE_API_URL` backend adresiniz olsun (yerelde genelde `http://127.0.0.1:8000`).

### 2) Backend

```powershell
cd project\backend
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`

### 3) Frontend

```powershell
cd project\frontend
npm install
npm run dev
```

Tarayıcı: `http://localhost:5173` — üstteki **1→9** şeridi ve sayfa başlıkları demo sırasını gösterir.

---

## Frontend demo akışı (özet)

| Adım | Kullanıcı aksiyonu |
|------|---------------------|
| 1 | CSV seç veya **“Demo: ecommerce_good.csv”** — `public/demo/` içindeki dosyayı yükler; ardından **profil** çağrılır. |
| 2–4 | Önizleme tablosu + kolon listesi; **validation** ve **quality** (şablon seçici; varsayılan `churn`). |
| 5–6 | Plan oluşturulur (`POST /datasets/{id}/plans`); **Planı onayla** (`POST /plans/{id}/approve`). |
| 7–8 | **Job başlat** → polling → **sonuç** (`/plans/.../jobs`, `/jobs/...`, `/jobs/.../result`). |
| 9 | Sonuç ekranında metrikler; sağda **Explain** (`POST /agent/explain`, otomatik + Yenile). |

**Demo CSV butonu:** Yerel dosya seçmeden örnek veriyle devam etmek içindir; aynı içerik `datasets/demo/ecommerce_good.csv` ile uyumludur.

Ayrıntılı anlatım: **[`docs/DEMO_FLOW.md`](docs/DEMO_FLOW.md)**  
Dağıtım: **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)**

---

## `LLM_PROVIDER=mock` ile anahtarsız demo

`.env` içinde:

```env
LLM_PROVIDER=mock
```

Plan üretimi ve explain uçları **dış LLM API’sine gitmeden** mock yanıt kullanır; portföy ve CI için uygundur. Gerçek anahtarlar için `backend/.env.example` içindeki OpenAI / Gemini / Ollama satırlarına bakın.

---

## Test ve build

### Backend

```powershell
cd project\backend
pytest tests/ -q
pytest tests/ -q --cov=. --cov-report=term-missing:skip-covered --cov-config=.coveragerc
```

Testler dış ağa güvenmeyecek şekilde tasarlanmıştır (`conftest`, mock LLM); ayrıntı `project/backend/tests/conftest.py`.

### Frontend

```powershell
cd project\frontend
npm run build
```

---

## Problem ve çözüm (kısa)

Ham CSV’ler farklı kolon adları ve kalite sorunları taşır. Bu projede:

- **Hibrit kolon eşleştirme** + LLM planının profille birleştirilmesi  
- **Pydantic plan şeması** ve **registry executor**  
- **Plan snapshot** + **onay** sonrası job veya senkron analyze  
- **Deterministik validation / quality** (LLM dışı)

---

## Teknoloji stack

- Backend: Python, FastAPI, SQLAlchemy, Pandas, scikit-learn, Pydantic v2  
- Veri: PostgreSQL (`DATABASE_URL`)  
- LLM: `LLM_PROVIDER=mock | openai | gemini | ollama`  
- Frontend: React, Vite, Tailwind  
- CORS: `CORS_ORIGINS` (virgülle ayrılmış); yoksa `http://localhost:5173`

---

## Diğer dokümanlar

- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**  
- **[`docs/API_EXAMPLES.md`](docs/API_EXAMPLES.md)**

---

## LLM güvenlik sınırları

- LLM SQL çalıştırmaz; registry dışı adımlar şema ile reddedilir.  
- Job ve analyze, **onaylı plan** kurallarına uyar.  
- API anahtarları yalnızca `.env` / barındırıcı secret’larında tutulmalı; **repoya commit edilmemeli**.

---

## Roadmap (öneri)

- Uplift vb.: `MlTemplate` + `templates/registry.py`  
- Alembic migration’ları  
- İsteğe bağlı job kuyruğu (RQ/Celery)  
- Daha zengin segmentasyon / satış tahmini UI testleri

---

## Lisans / iletişim

Portföy amaçlıdır; lisans ve iletişim bilgisini repoya eklemek isteyen kullanıcı bu bölümü güncelleyebilir.
