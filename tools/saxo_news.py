"""
Saxo Bank News Tool
Fetches recent news headlines and articles related to specific instruments
or free-text topics, using the Saxo Bank News API.

Usage:
    python tools/saxo_news.py --symbol AAPL
    python tools/saxo_news.py --symbol NVO --top 5
    python tools/saxo_news.py --uic 211 --asset-type Stock
    python tools/saxo_news.py --topic "Federal Reserve"
"""

import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

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


def get_news_for_instrument(uic: int, asset_type: str, top: int = 10) -> list:
    params = {
        "Uic": uic,
        "AssetType": asset_type,
        "$top": top,
    }
    response = requests.get(
        f"{BASE_URL}/news/v1/news",
        headers=get_headers(),
        params=params,
    )
    response.raise_for_status()
    return response.json().get("Data", [])


def get_news_by_topic(topic: str, top: int = 10) -> list:
    params = {
        "Keywords": topic,
        "$top": top,
    }
    response = requests.get(
        f"{BASE_URL}/news/v1/news",
        headers=get_headers(),
        params=params,
    )
    response.raise_for_status()
    return response.json().get("Data", [])


def format_article(article: dict) -> dict:
    return {
        "Headline": article.get("Headline"),
        "Summary": article.get("Summary", "")[:300] + ("..." if len(article.get("Summary", "")) > 300 else ""),
        "PublishDate": article.get("PublishDate"),
        "Source": article.get("SourceName"),
        "Id": article.get("Id"),
    }


def resolve_symbol(symbol: str) -> tuple:
    results = search_instruments(symbol, top=5)
    if not results:
        raise ValueError(f"No instrument found for symbol '{symbol}'")
    for r in results:
        if r.get("Symbol", "").upper() == symbol.upper():
            return r["Identifier"], r["AssetType"]
    best = results[0]
    return best["Identifier"], best["AssetType"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Saxo Bank news")
    parser.add_argument("--symbol", help="Ticker symbol to fetch news for")
    parser.add_argument("--uic", type=int, help="Instrument Uic")
    parser.add_argument("--asset-type", default="Stock", help="Asset type (default: Stock)")
    parser.add_argument("--topic", help="Free-text topic or keyword search")
    parser.add_argument("--top", type=int, default=10, help="Max articles (default: 10)")
    parser.add_argument("--raw", action="store_true", help="Print raw API response")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: SAXO_ACCESS_TOKEN is not set in .env")
        sys.exit(1)

    try:
        if args.symbol:
            print(f"Resolving '{args.symbol}'...")
            uic, asset_type = resolve_symbol(args.symbol)
            print(f"  -> Uic={uic}, AssetType={asset_type}")
            articles = get_news_for_instrument(uic, asset_type, args.top)

        elif args.uic:
            articles = get_news_for_instrument(args.uic, args.asset_type, args.top)

        elif args.topic:
            articles = get_news_by_topic(args.topic, args.top)

        else:
            print("ERROR: Provide --symbol, --uic, or --topic")
            sys.exit(1)

    except (ValueError, requests.HTTPError) as e:
        if hasattr(e, "response"):
            print(f"ERROR: {e.response.status_code} {e.response.text}")
        else:
            print(f"ERROR: {e}")
        sys.exit(1)

    if not articles:
        print("No news articles found.")
        sys.exit(0)

    if args.raw:
        print(json.dumps(articles, indent=2))
    else:
        formatted = [format_article(a) for a in articles]
        print(json.dumps(formatted, indent=2))
        print(f"\n{len(formatted)} article(s) found")
