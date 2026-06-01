"""Kolon eşleştirme: alias / exact."""

from __future__ import annotations

from services.column_matching import match_columns_hybrid, merge_llm_column_map_with_hybrid


def test_invoice_date_maps_order_date():
    cols = ["Customer ID", "InvoiceDate", "Quantity", "Price", "Invoice"]
    r = match_columns_hybrid(cols)
    assert r.fields["customer_id"].matched_column == "Customer ID"
    assert r.fields["order_date"].matched_column == "InvoiceDate"
    assert r.fields["unit_price"].matched_column == "Price"


def test_merge_preserves_uplift_column_map_keys():
    cols = [
        "CustomerID",
        "CampaignSent",
        "Purchased",
        "CampaignDate",
        "Revenue",
        "Channel",
        "Recency",
        "Frequency",
        "Monetary",
    ]
    report = match_columns_hybrid(cols)
    llm_map = {
        "customer_id": "CustomerID",
        "treatment": "CampaignSent",
        "outcome": "Purchased",
        "campaign_date": "CampaignDate",
    }
    merged = merge_llm_column_map_with_hybrid(llm_map, report, set(cols))
    assert merged["customer_id"] == "CustomerID"
    assert merged["treatment"] == "CampaignSent"
    assert merged["outcome"] == "Purchased"
    assert merged["campaign_date"] == "CampaignDate"
