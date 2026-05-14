"""Kolon eşleştirme: alias / exact."""

from __future__ import annotations

from services.column_matching import match_columns_hybrid


def test_invoice_date_maps_order_date():
    cols = ["Customer ID", "InvoiceDate", "Quantity", "Price", "Invoice"]
    r = match_columns_hybrid(cols)
    assert r.fields["customer_id"].matched_column == "Customer ID"
    assert r.fields["order_date"].matched_column == "InvoiceDate"
    assert r.fields["unit_price"].matched_column == "Price"
