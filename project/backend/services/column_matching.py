"""
Deterministik + hafif fuzzy kolon eşleştirme (LLM executor değil).
Profil kolon adları → platform standart alanları (customer_id, order_date, ...).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

Method = Literal["exact", "alias", "fuzzy", "llm", "missing"]

# Zorunlu / güçlü önerilen standart anahtarlar (sıra: greedy atamada kullanılır)
REQUIRED_STANDARDS: tuple[str, ...] = ("customer_id", "order_date")
RECOMMENDED_STANDARDS: tuple[str, ...] = ("order_id", "quantity", "unit_price")
ALL_STANDARDS: tuple[str, ...] = REQUIRED_STANDARDS + RECOMMENDED_STANDARDS

# Türkçe + İngilizce aliaslar (görünen kolon adı varyantları; normalize edilerek eşlenir)
_ALIAS_PAIRS: tuple[tuple[str, str], ...] = (
    # customer_id
    ("customer_id", "customer_id"),
    ("customerid", "customer_id"),
    ("customer id", "customer_id"),
    ("musteri kodu", "customer_id"),
    ("musterikodu", "customer_id"),
    ("müşteri kodu", "customer_id"),
    ("müşteriid", "customer_id"),
    ("musteriid", "customer_id"),
    ("client_id", "customer_id"),
    ("userid", "customer_id"),
    ("user_id", "customer_id"),
    ("kullanici id", "customer_id"),
    ("kullaniciid", "customer_id"),
    # order_date
    ("order_date", "order_date"),
    ("orderdate", "order_date"),
    ("siparis tarihi", "order_date"),
    ("siparistarihi", "order_date"),
    ("fatura tarihi", "order_date"),
    ("faturatarihi", "order_date"),
    ("invoicedate", "order_date"),
    ("invoice date", "order_date"),
    ("transaction_date", "order_date"),
    ("islem tarihi", "order_date"),
    ("tarih", "order_date"),
    # order_id
    ("order_id", "order_id"),
    ("orderid", "order_id"),
    ("siparis no", "order_id"),
    ("siparisno", "order_id"),
    ("fatura no", "order_id"),
    ("faturano", "order_id"),
    ("invoice", "order_id"),
    ("invoice no", "order_id"),
    ("invoiceno", "order_id"),
    ("invoice_id", "order_id"),
    # quantity
    ("quantity", "quantity"),
    ("qty", "quantity"),
    ("adet", "quantity"),
    ("miktar", "quantity"),
    ("piece", "quantity"),
    # unit_price
    ("unit_price", "unit_price"),
    ("unitprice", "unit_price"),
    ("price", "unit_price"),
    ("birim fiyat", "unit_price"),
    ("birimfiyat", "unit_price"),
    ("unit price", "unit_price"),
)


def _norm_token(s: str) -> str:
    """Kıyaslama için: küçük harf, Unicode harf/rakam tut; ayırıcıları at."""
    s = s.casefold().strip()
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE)


_ALIAS_NORM_TO_STANDARD: dict[str, str] = {}
for _alias_text, _std in _ALIAS_PAIRS:
    _k = _norm_token(_alias_text)
    if _k and _k not in _ALIAS_NORM_TO_STANDARD:
        _ALIAS_NORM_TO_STANDARD[_k] = _std


@dataclass
class FieldMatch:
    standard: str
    matched_column: str | None
    confidence: float
    method: Method
    requires_user_confirmation: bool
    candidates: list[str] = field(default_factory=list)


@dataclass
class HybridColumnReport:
    """Profil kolonları üzerinden tam eşleşme → alias → fuzzy → LLM adayları."""

    fields: dict[str, FieldMatch]

    def to_prompt_json(self) -> str:
        payload = [
            {
                "standard": std,
                "matched_column": m.matched_column,
                "confidence": round(m.confidence, 4),
                "method": m.method,
                "requires_user_confirmation": m.requires_user_confirmation,
                "candidates": m.candidates[:8],
            }
            for std, m in self.fields.items()
        ]
        return json.dumps(payload, ensure_ascii=False)

    def to_debug_dict(self) -> dict[str, object]:
        return {
            std: {
                "matched_column": m.matched_column,
                "confidence": m.confidence,
                "method": m.method,
                "requires_user_confirmation": m.requires_user_confirmation,
                "candidates": m.candidates,
            }
            for std, m in self.fields.items()
        }


def _fuzzy_ratio(a: str, b: str) -> float:
    na, nb = _norm_token(a), _norm_token(b)
    if not na or not nb:
        return 0.0
    return float(SequenceMatcher(None, na, nb).ratio())


def _best_fuzzy_for_standard(
    std: str, cols: list[str], used: set[str], *, min_score: float
) -> tuple[str | None, float, list[str]]:
    """Kullanılmayan kolonlar arasında std ve alias hedefleriyle en iyi skor."""
    targets: list[str] = [std.replace("_", " "), std]
    for alias_text, sstd in _ALIAS_PAIRS:
        if sstd == std:
            targets.append(alias_text)

    scored: list[tuple[float, str]] = []
    for c in cols:
        if c in used:
            continue
        best_local = max((_fuzzy_ratio(c, t) for t in targets), default=0.0)
        scored.append((best_local, c))
    scored.sort(key=lambda x: (-x[0], x[1]))
    ambiguous = (
        len(scored) >= 2
        and (scored[0][0] - scored[1][0]) < 0.04
        and scored[0][0] < 0.92
    )

    if not scored or scored[0][0] < min_score:
        cand = [c for s, c in scored[:5] if s >= 0.45]
        return None, 0.0, cand

    best_s, best_c = scored[0]
    if ambiguous:
        cand = [c for _, c in scored[:5]]
        return None, best_s, cand
    return best_c, best_s, [c for _, c in scored[:3]]


def match_columns_hybrid(profile_column_names: list[str]) -> HybridColumnReport:
    """
    Sıra: exact (standart ad) → alias sözlüğü → fuzzy → aday listesi (LLM seçimi).
    Aynı CSV kolonu birden fazla standart alana atanmaz (greedy sıra).
    """
    cols = [c.strip() for c in profile_column_names if isinstance(c, str) and c.strip()]
    used: set[str] = set()
    out: dict[str, FieldMatch] = {}

    for std in ALL_STANDARDS:
        matched: str | None = None
        conf = 0.0
        meth: Method = "missing"
        ruc = False
        cands: list[str] = []

        # 1) exact: normalize(std) == normalize(col)
        nt_std = _norm_token(std.replace("_", ""))
        for c in cols:
            if c in used:
                continue
            if _norm_token(c) == nt_std or _norm_token(c) == _norm_token(std):
                matched, conf, meth = c, 1.0, "exact"
                break

        # 2) alias
        if matched is None:
            for c in cols:
                if c in used:
                    continue
                mapped = _ALIAS_NORM_TO_STANDARD.get(_norm_token(c))
                if mapped == std:
                    matched, conf, meth = c, 0.95, "alias"
                    break

        # 3) fuzzy
        if matched is None:
            fc, score, cands = _best_fuzzy_for_standard(std, cols, used, min_score=0.78)
            if fc and score >= 0.78:
                matched, conf, meth = fc, score, "fuzzy"
                ruc = score < 0.90

        # 4) LLM / missing: adayları bırak
        if matched is None:
            _, _, cands = _best_fuzzy_for_standard(std, cols, used, min_score=0.35)
            if cands:
                meth, ruc = "llm", True
            else:
                meth, ruc = "missing", True
            conf = 0.0

        if matched is not None:
            used.add(matched)

        out[std] = FieldMatch(
            standard=std,
            matched_column=matched,
            confidence=conf,
            method=meth,
            requires_user_confirmation=ruc,
            candidates=cands,
        )

    return HybridColumnReport(fields=out)


def merge_llm_column_map_with_hybrid(
    llm_column_map: dict[str, str],
    report: HybridColumnReport,
    allowed_profile_names: set[str],
) -> dict[str, str]:
    """
    Önce deterministik eşleşmeleri uygula (exact/alias güçlü; fuzzy eşik üstü).
    Kalan standart alanları geçerli LLM eşlemeleriyle doldur; çakışmada deterministik öncelikli.
    """
    merged: dict[str, str] = {}
    used_cols: set[str] = set()

    for std in ALL_STANDARDS:
        m = report.fields.get(std)
        if not m or not m.matched_column:
            continue
        col = m.matched_column
        if col not in allowed_profile_names:
            continue
        if m.method == "exact" or m.method == "alias":
            merged[std] = col
            used_cols.add(col)
        elif m.method == "fuzzy" and m.confidence >= 0.78:
            merged[std] = col
            used_cols.add(col)

    for std, col in llm_column_map.items():
        if std not in ALL_STANDARDS:
            continue
        if col not in allowed_profile_names:
            continue
        if std in merged:
            continue
        if col in used_cols:
            continue
        merged[std] = col
        used_cols.add(col)

    return merged


def sync_missing_required_columns(normalized_plan: dict) -> None:
    """Zorunlu ve LLM'in bildirdiği standart alanlar column_map'te yoksa listeye ekler."""
    cm = normalized_plan.get("column_map")
    if not isinstance(cm, dict):
        cm = {}
    out: list[str] = []
    for r in REQUIRED_STANDARDS:
        v = cm.get(r)
        if not isinstance(v, str) or not v.strip():
            out.append(r)
    prev = normalized_plan.get("missing_required_columns") or []
    if isinstance(prev, list):
        for m in prev:
            if not isinstance(m, str) or not m.strip():
                continue
            if m not in ALL_STANDARDS:
                continue
            v = cm.get(m)
            if not isinstance(v, str) or not v.strip():
                if m not in out:
                    out.append(m)
    normalized_plan["missing_required_columns"] = out


def merge_plan_flags_with_hybrid(normalized_plan: dict, report: HybridColumnReport) -> None:
    """normalized_plan üzerinde requires_user_confirmation / warnings günceller (yerinde)."""
    llm_ruc = bool(normalized_plan.get("requires_user_confirmation"))
    warns = list(normalized_plan.get("warnings") or [])
    if not isinstance(warns, list):
        warns = []

    for std, m in report.fields.items():
        if m.method == "fuzzy" and m.matched_column:
            warns.append(
                f"Hibrit kolon eşlemesi ({std}): fuzzy yöntemi; kullanıcı onayı önerilir ({m.matched_column})."
            )
        if m.method == "llm":
            warns.append(
                f"Hibrit kolon eşlemesi ({std}): otomatik eşleşme zayıf; LLM veya kullanıcı seçimi gerekli."
            )
        if m.method == "missing" and std in REQUIRED_STANDARDS:
            warns.append(
                f"Hibrit kolon eşlemesi ({std}): profil kolonlarında güvenli eşleşme bulunamadı."
            )

    # dedupe sırayı koru
    seen: set[str] = set()
    deduped: list[str] = []
    for w in warns:
        if isinstance(w, str) and w.strip() and w.strip() not in seen:
            seen.add(w.strip())
            deduped.append(w.strip())
    normalized_plan["warnings"] = deduped

    ruc = llm_ruc
    for m in report.fields.values():
        if m.requires_user_confirmation and m.method in ("fuzzy", "llm", "missing"):
            ruc = True
    normalized_plan["requires_user_confirmation"] = ruc
