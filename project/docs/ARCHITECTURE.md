# Mimari özeti

Bu proje, e‑ticaret işlem CSV’lerinden **güvenli bir analiz planı** üretip, onay sonrası **kayıtlı (registry) adımlarla** feature üretimi ve **şablon tabanlı ML** çalıştıran bir FastAPI backend’idir. Amaç: LLM’i “beyin” olarak kullanırken, kritik iş mantığını ve güvenliği sunucuda deterministik katmanlarda tutmak.

---

## LLM’in rolü

| Alan | Rol |
|------|-----|
| `POST /agent/analysis-plan` ve `POST /datasets/{id}/plans` | `generate_validated_analysis_plan`: sistem prompt’u + profil + hibrit kolon ipuçları ile **analysis_plan JSON** üretmek (veya `LLM_PROVIDER=mock` ile yerel örnek JSON). |
| `POST /agent/chat` | Serbest metin yanıtı (plan üretmez). |
| `POST /agent/explain` | Tamamlanmış model metriklerinden **yapılandırılmış açıklama JSON**’u (şema doğrulaması backend’de). |

LLM çıktısı her zaman **Pydantic şeması** ve ek kurallarla (`services/analysis_plan_normalize`, `merge_llm_column_map_with_hybrid`) doğrulanır; geçersiz plan API’de reddedilir.

---

## LLM’in yapmadıkları (bilinçli sınır)

- SQL veya ham veri tablosuna **doğrudan erişim yok**; veri okuma `pandas` + SQLAlchemy engine ile uygulama kodunda.
- **Cleaning / feature** adımlarını serbest seçemez: yalnızca `cleaning/registry.py` ve `features/registry.py` içinde kayıtlı string adlar kabul edilir.
- **Plan snapshot** onayı LLM’e bırakılmaz; kullanıcı/API `POST /plans/{plan_id}/approve` ile onaylar.
- **Model eğitimi** LLM tarafından çalıştırılmaz; `services/analysis_execution` + `ml/*` pipeline.

---

## Şablon tabanlı ML katmanı (`project/backend/templates/`)

- **`templates/base.MlTemplate`**: Şablon sözleşmesi — `minimum_rows` / `recommended_rows`, `to_execution_dict()` (eski `TEMPLATES` sözlüğü ile uyumlu), `build_pipeline(validated_plan)`, plan adımları için `validate_plan_steps()`, metrik sonrası `postprocess_metrics()`, validation eşikleri (`validation_recommended_*`, `compute_training_data_sufficient`).
- **`templates/registry.py`**: `get_template(name)` (dict), `get_template_spec(name)` (nesne), `ensure_template_registered()`, `list_template_names()`. **Kayıtlı olmayan şablon** (ör. gelecekteki `uplift`) LLM çıktısında bile çalıştırılamaz.
- **`templates/churn.py`**, **`segmentation.py`**, **`sales_forecast.py`**: Şablona özgü ham kolon beklentisi, pipeline kurulumu ve churn oranı uyarıları (churn) burada toplanır.
- **`schemas/analysis_plan.py`**: `VALID_TEMPLATES` artık `list_template_names()` ile registry’den türetilir — tek kaynak.
- **`ml/templates.py`**: Geriye dönük import; yeni kod `templates.registry` kullanmalı.

---

## Backend validation

- `GET /datasets/{dataset_id}/validation`: `validation/ecommerce_rules.py` — kolon eşleştirme, null oranları, tarih parse, duplicate, iş kuralları. **LLM kullanmaz.** İsteğe bağlı query: **`template`** (`churn` \| `segmentasyon` \| `satis_tahmini`); öneri eşikleri ve `churn_data_sufficient` hesabı seçilen şablona göre değişir (API alanı adı geriye dönük).
- `GET /datasets/{dataset_id}/quality`: Aynı `template` parametresi ile validation metrikleri üzerinden `validation/quality_score.py` skoru.
- `schemas/analysis_plan.py`: plan JSON şeması; bilinmeyen `cleaning_steps` / `feature_plan` / **kayıtlı olmayan template** reddedilir.

---

## Registry executor

`services/plan_executor.py` içinde `execute_analysis_plan`:

1. `column_map` ile DataFrame kolonlarının varlığını doğrular.
2. `cleaning_plan` içindeki her adımı `CLEANING_REGISTRY` üzerinden çalıştırır.
3. `feature_plan` (tek string adım) ile `FEATURE_REGISTRY` fonksiyonunu çağırır.

Bilinmeyen ad → `ValueError` → analiz/job hata mesajına dönüşür. Bu tasarım **arbitrary code execution** riskini azaltır.

---

## Plan snapshot

- `PlanSnapshot`: LLM + merge sonrası üretilen planın **immutable** kaydı (`payload_json`, `status`: `draft` | `approved` | `rejected`, `mapping_confidence_json`, `warnings_json`).
- Onaylanmış plan, `POST /analyze` veya `POST /plans/{plan_id}/jobs` ile çalıştırılabilir; payload `validated_plan_from_snapshot_payload` ile tekrar parse edilir.

---

## Job lifecycle

1. `POST /plans/{plan_id}/jobs` + body `{"dataset_id": ...}` → `AnalysisJob` (`queued`).
2. FastAPI `BackgroundTasks`: `services/analysis_job_tasks.run_analysis_job(job_id)` (ayrı DB oturumu).
3. Durum geçişleri: `queued` → `running` → `completed` | `failed`; `GET /jobs/{job_id}` ile izlenir.
4. Sonuç: `GET /jobs/{job_id}/result` (`completed` iken; `POST /analyze` ile uyumlu anahtarlar).

Uzun süren eğitim HTTP isteğini bloklamaz (job yolu).

---

## ML pipeline

- **Şablon çözümü:** `templates.registry.get_template_spec(template_name)` → `to_execution_dict()` + `build_pipeline(validated_plan)`.
- **Feature tablosu:** planlı yol `execute_analysis_plan` (çalıştırmadan önce şablona göre `validate_plan_steps`); legacy yol `column_map` ile SQL rename.
- **Minimum / önerilen satır:** şablon nesnesindeki `minimum_rows` / `recommended_rows` (`services/analysis_execution.run_analysis_training`).
- **Metrik son işleme:** `MlTemplate.postprocess_metrics` (churn oranı uyarıları `ChurnTemplate` içinde).
- Metrikler: pipeline içi train/test split ve **metric_warnings** (küçük test seti, dengesiz sınıf, “perfect metrics” şüphesi vb.).

**Not:** `ml/templates.py` yalnızca uyumluluk katmanıdır; iş kuralları `templates/` altındadır.

---

## Neden “güvenli” mimari?

1. **İki aşamalı plan**: taslak → insan/onay API’si → çalıştırma.
2. **Allowlist** executor: yalnızca kayıtlı cleaning/feature fonksiyonları.
3. **Deterministik validation** veri kalitesi ve şema için LLM’e güvenilmez.
4. **Şablon registry**: yeni ML iş akışları tek kaynaktan kayıt edilir; LLM yalnızca kayıtlı `recommended_template` değerleri üretebilir (`agent/prompt_builder` şablon listesini registry’den alır).
5. **Ayrı job süreci**: zaman aşımı ve kullanıcı deneyimi için HTTP’den ayrılmış çalışma (basit BackgroundTasks; harici queue yok).
6. **Mock provider**: geliştirme ve testte dış LLM API’si zorunlu değil (`LLM_PROVIDER=mock`).

Bu proje **Kafka / dağıtık orchestration** içermez; portföy kapsamında bilinçli sadeleştirmedir.
