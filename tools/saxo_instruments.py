"""
Saxo Bank Instrument Search Tool
Resolves a ticker symbol or company name to a Saxo Bank Uic + AssetType,
which are required for price lookups and other instrument-specific calls.

Usage:
    python tools/saxo_instruments.py AAPL
    python tools/saxo_instruments.py "Novo Nordisk"
    python tools/saxo_instruments.py TSLA --asset-type Stock
    python tools/saxo_instruments.py EURUSD --asset-type FxSpot
"""

import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SAXO_ACCESS_TOKEN")
ENVIRONMENT = os.getenv("SAXO_ENVIRONMENT", "sim")
BASE_URL = (
    "https://gateway.saxobank.com/sim/openapi"
    if ENVIRONMENT == "sim"
    else "https://gateway.saxobank.com/openapi"
)

# Most common asset types for equity/ETF searches
DEFAULT_ASSET_TYPES = "Stock,Etf,Fund,Bond,FxSpot"


def get_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def search_instruments(query: str, asset_type: str = None, top: int = 10) -> list:
    params = {
        "Keywords": query,
        "$top": top,
        "IncludeNonTradable": False,
    }
    if asset_type:
        params["AssetTypes"] = asset_type
    else:
        params["AssetTypes"] = DEFAULT_ASSET_TYPES

    response = requests.get(
        f"{BASE_URL}/ref/v1/instruments",
        headers=get_headers(),
        params=params,
    )
    response.raise_for_status()
    return response.json().get("Data", [])


def format_instrument(inst: dict) -> dict:
    return {
        "Uic": inst.get("Identifier"),
        "AssetType": inst.get("AssetType"),
        "Symbol": inst.get("Symbol"),
        "Description": inst.get("Description"),
        "ExchangeId": inst.get("ExchangeId"),
        "CurrencyCode": inst.get("CurrencyCode"),
        "SummaryType": inst.get("SummaryType"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search Saxo Bank instruments")
    parser.add_argument("query", help="Ticker symbol or company name to search")
    parser.add_argument("--asset-type", help="Filter by asset type (e.g. Stock, Etf, FxSpot)")
    parser.add_argument("--top", type=int, default=10, help="Max results (default: 10)")
    parser.add_argument("--raw", action="store_true", help="Print raw API response")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: SAXO_ACCESS_TOKEN is not set in .env")
        sys.exit(1)

    try:
        results = search_instruments(args.query, args.asset_type, args.top)
    except requests.HTTPError as e:
        print(f"ERROR: {e.response.status_code} {e.response.text}")
        sys.exit(1)

    if not results:
        print(f"No instruments found for '{args.query}'")
        sys.exit(0)

    if args.raw:
        print(json.dumps(results, indent=2))
    else:
        formatted = [format_instrument(i) for i in results]
        print(json.dumps(formatted, indent=2))
        print(f"\n{len(formatted)} result(s) for '{args.query}'")
