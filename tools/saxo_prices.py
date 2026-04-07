"""
Saxo Bank Price Tool
Fetches current quote (bid/ask/last/change) for one or more instruments.
Requires a Uic and AssetType — use saxo_instruments.py to resolve these.

Usage:
    python tools/saxo_prices.py --uic 211 --asset-type Stock
    python tools/saxo_prices.py --uic 211 --asset-type Stock --uic 1549 --asset-type Stock
    python tools/saxo_prices.py --symbol AAPL
    python tools/saxo_prices.py --symbol TSLA --symbol NVO
"""

import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

# Import instrument search from sibling tool
sys.path.insert(0, os.path.dirname(__file__))
from saxo_instruments import search_instruments

load_dotenv()

TOKEN = os.getenv("SAXO_ACCESS_TOKEN")
ENVIRONMENT = os.getenv("SAXO_ENVIRONMENT", "sim")
BASE_URL = (
    "https://gateway.saxobank.com/sim/openapi"
    if ENVIRONMENT == "sim"
    else "https://gateway.saxobank.com/openapi"
)


def get_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def get_quote(uic: int, asset_type: str) -> dict:
    params = {
        "Uic": uic,
        "AssetType": asset_type,
        "FieldGroups": "Quote,DisplayAndFormat,InstrumentPriceDetails",
    }
    response = requests.get(
        f"{BASE_URL}/trade/v1/infoprices",
        headers=get_headers(),
        params=params,
    )
    response.raise_for_status()
    return response.json()


def get_quotes_batch(instruments: list) -> list:
    """instruments: list of {"Uic": int, "AssetType": str}"""
    params = {
        "Uics": ",".join(str(i["Uic"]) for i in instruments),
        "AssetType": instruments[0]["AssetType"],  # batch requires same asset type
        "FieldGroups": "Quote,DisplayAndFormat,InstrumentPriceDetails",
    }
    response = requests.get(
        f"{BASE_URL}/trade/v1/infoprices/list",
        headers=get_headers(),
        params=params,
    )
    response.raise_for_status()
    return response.json().get("Data", [])


def format_quote(data: dict) -> dict:
    q = data.get("Quote", {})
    fmt = data.get("DisplayAndFormat", {})
    details = data.get("InstrumentPriceDetails", {})

    # SIM accounts without a data subscription return NoAccess
    no_access = (
        q.get("PriceTypeAsk") == "NoAccess" or q.get("PriceTypeBid") == "NoAccess"
    )
    if no_access:
        return {
            "Symbol": fmt.get("Symbol"),
            "Description": fmt.get("Description"),
            "Currency": fmt.get("Currency"),
            "Error": "NoAccess — SIM trial account has no real-time data subscription. Use finnhub_prices.py instead.",
            "Uic": data.get("Uic"),
            "AssetType": data.get("AssetType"),
        }

    return {
        "Symbol": fmt.get("Symbol"),
        "Description": fmt.get("Description"),
        "Currency": fmt.get("Currency"),
        "LastTraded": q.get("Last") or q.get("Mid"),
        "Bid": q.get("Bid"),
        "Ask": q.get("Ask"),
        "DailyChangePercent": details.get("PercentChange"),
        "PriceDelay": q.get("DelayedByMinutes", 0),
        "Uic": data.get("Uic"),
        "AssetType": data.get("AssetType"),
    }


def resolve_symbol(symbol: str) -> tuple:
    """Returns (uic, asset_type) for the best match of a symbol."""
    results = search_instruments(symbol, top=5)
    if not results:
        raise ValueError(f"No instrument found for symbol '{symbol}'")
    # Prefer exact symbol match
    for r in results:
        if r.get("Symbol", "").upper() == symbol.upper():
            return r["Identifier"], r["AssetType"]
    # Fall back to first result
    best = results[0]
    return best["Identifier"], best["AssetType"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Saxo Bank instrument prices")
    parser.add_argument("--uic", type=int, action="append", dest="uics", help="Instrument Uic")
    parser.add_argument("--asset-type", action="append", dest="asset_types", help="Asset type (paired with --uic)")
    parser.add_argument("--symbol", action="append", dest="symbols", help="Ticker symbol to auto-resolve")
    parser.add_argument("--raw", action="store_true", help="Print raw API response")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: SAXO_ACCESS_TOKEN is not set in .env")
        sys.exit(1)

    instruments = []

    # Resolve symbols to uic+asset_type
    if args.symbols:
        for sym in args.symbols:
            print(f"Resolving '{sym}'...")
            try:
                uic, asset_type = resolve_symbol(sym)
                instruments.append({"Uic": uic, "AssetType": asset_type, "_symbol": sym})
                print(f"  -> Uic={uic}, AssetType={asset_type}")
            except (ValueError, requests.HTTPError) as e:
                print(f"  ERROR: {e}")

    # Direct uic+asset_type pairs
    if args.uics:
        asset_types = args.asset_types or ["Stock"] * len(args.uics)
        for uic, asset_type in zip(args.uics, asset_types):
            instruments.append({"Uic": uic, "AssetType": asset_type})

    if not instruments:
        print("ERROR: Provide --symbol or --uic/--asset-type")
        sys.exit(1)

    results = []
    for inst in instruments:
        try:
            raw = get_quote(inst["Uic"], inst["AssetType"])
            results.append(raw if args.raw else format_quote(raw))
        except requests.HTTPError as e:
            print(f"ERROR fetching Uic={inst['Uic']}: {e.response.status_code} {e.response.text}")

    print(json.dumps(results, indent=2))
