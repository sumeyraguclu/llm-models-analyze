# Dağıtım — Vercel + Render + Neon (önerilen demo stack)

Bu rehber **en az sürtünme** ile çalışan demo hedefler: anahtarsız **`LLM_PROVIDER=mock`**, ücretsiz katmanlarla mümkün olduğunca uyumlu adımlar.

| Bileşen | Platform | Rol |
|---------|-----------|-----|
| Veritabanı | **Neon** PostgreSQL | `DATABASE_URL` |
| Backend | **Render** Web Service | FastAPI, `PORT`, `/health` |
| Frontend | **Vercel** | Vite build, `VITE_API_URL` |

**Railway** alternatifi: Render ile aynı ortam değişkenleri; repo kökü `project/backend`, Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`, Health: `/health`.

---

## Önkoşullar

- GitHub’da repo (ör. `aProject` kökünde `project/backend` ve `project/frontend`).
- Render Blueprint için **iki seçenekten biri**:
  - **A)** Repo kökü `aProject` (üst klasörde `project/`) → kökteki `render.yaml` (`rootDir: project/backend`).
  - **B)** Repo kökü yalnızca `project/` → `project/render.yaml` (`rootDir: backend`).

---

## 1) Neon PostgreSQL

1. [Neon](https://neon.tech) → proje oluştur → **Connection string** kopyala.
2. Bağlantıda **`sslmode=require`** olduğundan emin olun (Neon genelde ekler).
3. String `postgres://` veya `postgresql://` ile başlayabilir — backend bunu **`postgresql+psycopg2://`** olarak normalize eder.

---

## 2) Render — backend

1. [Render](https://render.com) → **New** → **Blueprint** (veya **Web Service**).
2. Repo’yu bağla; Blueprint kullanıyorsanız uygun `render.yaml` yolunu seçin.
3. **Environment** (Blueprint dışı manuel serviste):
   - `DATABASE_URL` = Neon connection string (secret).
   - `LLM_PROVIDER` = `mock` (dış LLM anahtarı gerekmez).
   - `CORS_ORIGINS` = Vercel URL’iniz + isteğe bağlı yerel geliştirme, **virgülle**, örnek:  
     `https://automl-demo.vercel.app,http://localhost:5173`
   - `PYTHONUNBUFFERED` = `1` (log için; isteğe bağlı).
4. **Build:** `pip install -r requirements.txt`  
5. **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`  
6. **Health check path:** `/health`  
7. Deploy sonrası URL örn. `https://automl-agent-api.onrender.com` — **HTTPS**, sonunda `/` yok.

**Notlar**

- `runtime.txt` (`project/backend/runtime.txt`) Render Python sürümünü sabitler (**3.12.8**).
- `Procfile` Railway / bazı ortamlar için aynı start komutunu içerir.
- İlk deploy’da `main.py` içindeki `create_all` tabloları oluşturur (Alembic yok; demo yeterli).
- Job’lar **Redis kullanmaz**; FastAPI `BackgroundTasks` aynı worker’da çalışır. Uzun eğitimde Render **request timeout** (ücretsiz planda düşük) riski — demo CSV ile genelde sorun olmaz.

---

## 3) Vercel — frontend

1. [Vercel](https://vercel.com) → **Add New** → **Project** → GitHub repo.
2. **Root Directory:** `project/frontend`
3. **Framework Preset:** Vite (veya `vercel.json` içindeki `framework: vite`).
4. **Environment Variables** (Build time):
   - `VITE_API_URL` = Render backend kök URL’si, örn. `https://automl-agent-api.onrender.com` (**sonunda slash yok**).
5. Deploy. Üretim URL’si örn. `https://xxx.vercel.app`.

**Son adım:** Render’da `CORS_ORIGINS` içine bu Vercel URL’ini ekleyin (veya Blueprint’te güncelleyip yeniden deploy). Aksi halde tarayıcı CORS hatası verir.

---

## 4) Doğrulama

Tarayıcıdan:

- `GET https://<render-host>/health` → `{"status":"ok"}`
- `GET https://<render-host>/ready` → `{"status":"ready"}` (Neon erişilebilirse)

Frontend: demo akışıyla CSV yükleme → plan → job → sonuç.

---

## Ortam değişkenleri özeti

| Değişken | Nerede | Örnek / not |
|----------|--------|-------------|
| `DATABASE_URL` | Render | Neon (SSL) |
| `LLM_PROVIDER` | Render | `mock` |
| `CORS_ORIGINS` | Render | `https://....vercel.app,http://localhost:5173` |
| `VITE_API_URL` | Vercel (build) | `https://....onrender.com` |

Şablonlar: [`backend/.env.example`](../backend/.env.example), [`frontend/.env.example`](../frontend/.env.example).

---

## Sorun giderme

| Belirti | Olası neden |
|---------|-------------|
| `/ready` 503 | `DATABASE_URL` yanlış, Neon uyku, firewall, veya `sslmode` eksik |
| CORS | `CORS_ORIGINS` tam eşleşme; `www` vs non-www, `http` vs `https` |
| Frontend API 404 | `VITE_API_URL` yanlış veya sonunda `/` — düzeltip **yeniden build** |
| DB driver hatası | URL `postgres://` kaldı; güncel kod `database.py` ile normalize olmalı |

---

## Güvenlik

- `.env` / Neon / LLM anahtarlarını **repoya koymayın** ([`project/.gitignore`](../.gitignore)).
- Demo için **`LLM_PROVIDER=mock`** yeterlidir; gerçek anahtarları yalnızca gizli ortam değişkenlerinde tutun.

---

## Yerel / CI

```powershell
cd project\backend
pytest tests/ -q
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
cd project\frontend
npm run build
```

Daha genel mimari özeti: [`README.md`](../README.md), kullanıcı demosu: [`DEMO_FLOW.md`](DEMO_FLOW.md).
