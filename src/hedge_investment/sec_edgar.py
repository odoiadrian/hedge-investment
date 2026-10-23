"""Small read-only connector for public SEC company facts."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
FACTS_OF_INTEREST = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ),
    "net_income": ("NetIncomeLoss",),
    "total_assets": ("Assets",),
    "cash_and_equivalents": ("CashAndCashEquivalentsAtCarryingValue",),
    "stockholders_equity": ("StockholdersEquity",),
}


class SecDataError(RuntimeError):
    """Raised when SEC data cannot be retrieved or interpreted."""


def _get_json(url: str, user_agent: str) -> Any:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SecDataError(f"SEC request failed for {url}: {exc}") from exc


def _ticker_to_cik(user_agent: str) -> dict[str, str]:
    raw = _get_json(TICKER_URL, user_agent)
    entries = raw.values() if isinstance(raw, dict) else ()
    return {
        str(entry["ticker"]).upper(): str(entry["cik_str"]).zfill(10)
        for entry in entries
        if isinstance(entry, dict) and "ticker" in entry and "cik_str" in entry
    }


def _latest_fact(companyfacts: dict[str, Any], concepts: tuple[str, ...]) -> dict[str, Any] | None:
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    candidates: list[dict[str, Any]] = []
    concept_name = ""
    for concept in concepts:
        details = gaap.get(concept)
        if not isinstance(details, dict):
            continue
        units = details.get("units", {})
        for unit_name, facts in units.items():
            for fact in facts:
                if fact.get("form") in {"10-K", "10-Q", "20-F", "40-F"}:
                    candidates.append({**fact, "unit": unit_name})
        if candidates:
            concept_name = concept
            break
    if not candidates:
        return None
    # The most recently filed company fact is useful for a current snapshot, but
    # it is not a point-in-time dataset and may describe a quarter or fiscal year.
    latest = max(candidates, key=lambda fact: (fact.get("filed", ""), fact.get("end", "")))
    return {
        "concept": concept_name,
        "value": latest.get("val"),
        "unit": latest.get("unit"),
        "period_start": latest.get("start"),
        "period_end": latest.get("end"),
        "filed": latest.get("filed"),
        "form": latest.get("form"),
        "fiscal_year": latest.get("fy"),
        "fiscal_period": latest.get("fp"),
        "accession": latest.get("accn"),
    }


def fetch_company_facts(tickers: list[str], cik_by_ticker: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fetch latest reported SEC facts for tickers or explicitly supplied CIKs."""
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise SecDataError(
            "Set SEC_USER_AGENT to an application name and contact email before requesting SEC data."
        )

    resolved_ciks = dict(cik_by_ticker or {})
    unresolved = [ticker for ticker in tickers if ticker.upper() not in resolved_ciks]
    if unresolved:
        ticker_map = _ticker_to_cik(user_agent)
        for ticker in unresolved:
            cik = ticker_map.get(ticker.upper())
            if cik is None:
                raise SecDataError(f"Ticker {ticker!r} was not found in the SEC company ticker list.")
            resolved_ciks[ticker.upper()] = cik

    results: list[dict[str, Any]] = []
    for ticker in tickers:
        cik = resolved_ciks[ticker.upper()].zfill(10)
        url = FACTS_URL.format(cik=cik)
        payload = _get_json(url, user_agent)
        facts = {
            name: latest
            for name, concepts in FACTS_OF_INTEREST.items()
            if (latest := _latest_fact(payload, concepts)) is not None
        }
        results.append({
            "ticker": ticker,
            "company": payload.get("entityName"),
            "cik": cik,
            "source": url,
            "facts": facts,
        })
    return results
