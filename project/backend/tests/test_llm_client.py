"""LLM client: mock yolları, fence temizliği — network yok."""

from __future__ import annotations

import json

import pytest

from services import llm_client


def test_mock_returns_parseable_plan(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    raw = llm_client.call_llm("system", "user", structured_json=False)
    obj = json.loads(raw)
    assert obj.get("recommended_template") == "churn" or obj.get("template") == "churn"
    assert "column_map" in obj


def test_mock_explain_when_system_has_schema_keywords(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    raw = llm_client.call_llm(
        "Return JSON with key_findings array.\n",
        "Explain metrics.",
        structured_json=True,
    )
    obj = json.loads(raw)
    assert "summary" in obj and "key_findings" in obj


def test_clean_llm_response_json_fence():
    wrapped = '```json\n{"a": 1}\n```'
    out = llm_client._clean_llm_response(wrapped)
    assert json.loads(out) == {"a": 1}


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "skynet")
    with pytest.raises(ValueError, match="Bilinmeyen LLM_PROVIDER"):
        llm_client.call_llm("s", "u")
