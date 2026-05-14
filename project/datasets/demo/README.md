# Demo CSV dosyaları

Bu klasördeki örnekler, `POST /ingest/csv` ile yüklenip profil, validasyon ve (uygunsa) churn analizi demo’ları için kullanılabilir. **Gerçek müşteri verisi değildir**; sentetik örneklerdir.

Yükleme örneği (API çalışırken):

```http
POST /ingest/csv
Content-Type: multipart/form-data
```

`csv_file` alanına aşağıdaki dosyalardan birini gönderin.

---

## `ecommerce_good.csv`

**Senaryo:** İşlem satırlı e‑ticaret verisi; standart kolon isimleri (`Customer ID`, `InvoiceDate`, `Invoice`, `Quantity`, `Price`). Yaklaşık 150 müşteri × birkaç işlem.

**Beklenen davranış**

- `GET /datasets/{id}/validation`: `is_valid: true` olasılığı yüksek; `customer_id` / `order_date` eşleşmesi net.
- `GET /datasets/{id}/quality`: Skor genelde **good** veya sınırda **warning** (veri boyutuna göre).
- Churn / plan akışı: Backend’in önerdiği minimum satır sayılarına yaklaştığı için **tam pipeline** (profil → plan → onay → job veya senkron `POST /analyze`) için uygundur.

---

## `ecommerce_bad_quality.csv`

**Senaryo:** Aynı kolon isimleri korunur; ancak müşteri kimliği çok boş, negatif miktar, sıfır fiyat ve dar müşteri çeşitliliği kasıtlı olarak yüksektir.

**Beklenen davranış**

- Validation: `is_valid` false veya çok sayıda **warnings** / **errors** (boş müşteri oranı, negatif miktar, fiyat ≤ 0).
- Quality: `overall_score` düşük veya **poor** / **warning** seviyesi; `transaction_quality` ve `identity_quality` bileşenleri cezalanır.
- Analiz: Bu dosyayı “veri kalitesi uyarıları” demo’sunda kullanın; üretim churn eğitimi öncesi temizlik adımlarının etkisini göstermek içindir.

---

## `ecommerce_missing_columns.csv`

**Senaryo:** Sadece `SKU` ve `Amount` kolonları; platformun beklediği `customer_id` / `order_date` vb. yapı yok.

**Beklenen davranış**

- Validation: `is_valid: false`; `customer_id` ve `order_date` eşlenemediği için hata mesajları.
- Quality: Metrikler kısıtlı veya anlamlı değil; skor düşük.
- Analiz: **Churn / plan çalıştırma için uygun değil**; “eksik şema / red” demo’su için idealdir.

---

## `ecommerce_small_dataset.csv`

**Senaryo:** Kolonlar doğru formatta ancak yalnızca **8 müşteri**, işlem sayısı çok düşük.

**Beklenen davranış**

- Validation: Çoğu kural geçer olsa da `churn_data_sufficient: false` ve “daha fazla müşteri / satır önerilir” uyarıları beklenir.
- Quality: Skor genelde **warning** veya **good** alt bandı (satır / müşteri derinliği düşük).
- Analiz: UI’da uyarı metinleri ve düşük veri uyarısı (`RECOMMENDED_ROWS` altı) göstermek için uygundur; **minimum churn müşteri eşiğini** geçmeyebilir (`insufficient_data` hatası alınabilir).

---

## Notlar

- Demo sırasında `LLM_PROVIDER=mock` kullanırsanız plan üretimi yerel mock JSON ile çalışır; gerçek API anahtarı gerekmez.
- Üretimde kullanmadan önce kendi CSV şemanızı `GET .../validation` ile doğrulayın.
