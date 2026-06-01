# Demo CSV dosyaları



Resmi demo kaynakları `autoMLdatasets/` klasöründen üretilir. Gerçek veridir; akademik çalışmalarda kullanılır. Boyutlar uygulama performansı için kısaltılmıştır.



## Varsayılan demo dosyaları (UI)



| Modül | Varsayılan demo dosyası | Açıklama |

| ----- | ----------------------- | -------- |

| Churn | `ecommerce_good.csv` | İşlem düzeyi e-ticaret verisi; mevcut churn pipeline ile uyumlu |

| Uplift | `hillstrom_uplift_demo.csv` | Treatment/outcome içeren kampanya verisi |

| Segmentasyon | `online_retail_II_demo.csv` | RFM tabanlı segmentasyon için e-ticaret işlem verisi |



## Diğer dosyalar



| Dosya | Rol | Açıklama |

| ----- | --- | -------- |

| `WA_Fn-UseC_-Telco-Customer-Churn.csv` | Ham referans | IBM Telco — tam kopya (~7 043 müşteri); **varsayılan churn demo değil** |

| `telco_churn_transactions_demo.csv` | Türev / referans | Telco’dan sentetik işlem grain; pipeline ile uyumsuz metrik riski; **UI churn butonu bunu kullanmaz** |

| `hillstrom_uplift_demo.csv` | Uplift (UI) | Hillstrom — ilk 20 000 satır |

| `uplift_campaign_demo.csv` | Uplift (test) | Hillstrom ile aynı içerik (pytest geriye uyumu) |

| `ecommerce_bad_quality.csv`, … | Kalite senaryoları | Validasyon / kalite testleri |



Üretim (Telco ham + türev, Hillstrom, Online Retail):



```bash

python project/backend/scripts/prepare_official_demo_datasets.py

```



Yükleme: `POST /ingest/csv` · Demo sırasında `LLM_PROVIDER=mock` önerilir.

