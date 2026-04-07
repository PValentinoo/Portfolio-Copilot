"""
Finnhub Tool — Prices and News
Provides real-time/delayed stock quotes and company news via Finnhub.
Used as the price and news backend since Saxo SIM has no data subscription.

Requires: FINNHUB_API_KEY in .env (https://finnhub.io/ — free tier available)

Usage:
    python tools/finnhub.py quote AAPL
    python tools/finnhub.py quote AAPL TSLA NVO
    python tools/finnhub.py news AAPL
    python tools/finnhub.py news AAPL --days 3
    python tools/finnhub.py profile AAPL
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"


def get_params(extra: dict = None) -> dict:
    params = {"token": API_KEY}
    if extra:
        params.update(extra)
    return params


def get_quote(symbol: str) -> dict:
    r = requests.get(f"{BASE_URL}/quote", params=get_params({"symbol": symbol}))
    r.raise_for_status()
    data = r.json()
    return {
        "Symbol": symbol.upper(),
        "Current": data.get("c"),
        "Open": data.get("o"),
        "High": data.get("h"),
        "Low": data.get("l"),
        "PreviousClose": data.get("pc"),
        "ChangePercent": round((data["c"] - data["pc"]) / data["pc"] * 100, 2)
        if data.get("c") and data.get("pc")
        else None,
        "Timestamp": datetime.fromtimestamp(data["t"], tz=timezone.utc).isoformat()
        if data.get("t")
        else None,
    }


def get_company_news(symbol: str, days: int = 7) -> list:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    r = requests.get(
        f"{BASE_URL}/company-news",
        params=get_params({"symbol": symbol, "from": str(start), "to": str(end)}),
    )
    r.raise_for_status()
    articles = r.json()
    return [
        {
            "Headline": a.get("headline"),
            "Summary": (a.get("summary", "")[:300] + "...") if len(a.get("summary", "")) > 300 else a.get("summary"),
            "Source": a.get("source"),
            "URL": a.get("url"),
            "PublishedAt": datetime.fromtimestamp(a["datetime"], tz=timezone.utc).isoformat()
            if a.get("datetime")
            else None,
        }
        for a in articles
    ]


def get_company_profile(symbol: str) -> dict:
    r = requests.get(
        f"{BASE_URL}/stock/profile2",
        params=get_params({"symbol": symbol}),
    )
    r.raise_for_status()
    data = r.json()
    return {
        "Name": data.get("name"),
        "Symbol": data.get("ticker"),
        "Exchange": data.get("exchange"),
        "Industry": data.get("finnhubIndustry"),
        "Country": data.get("country"),
        "Currency": data.get("currency"),
        "MarketCap": data.get("marketCapitalization"),
        "Shares": data.get("shareOutstanding"),
        "WebURL": data.get("weburl"),
    }


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: FINNHUB_API_KEY is not set in .env")
        print("Get a free key at https://finnhub.io/")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Finnhub price and news tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # quote
    q_parser = subparsers.add_parser("quote", help="Get stock quote(s)")
    q_parser.add_argument("symbols", nargs="+", help="One or more ticker symbols")

    # news
    n_parser = subparsers.add_parser("news", help="Get company news")
    n_parser.add_argument("symbol", help="Ticker symbol")
    n_parser.add_argument("--days", type=int, default=7, help="Days of history (default: 7)")
    n_parser.add_argument("--top", type=int, default=10, help="Max articles (default: 10)")

    # profile
    p_parser = subparsers.add_parser("profile", help="Get company profile")
    p_parser.add_argument("symbol", help="Ticker symbol")

    args = parser.parse_args()

    try:
        if args.command == "quote":
            results = [get_quote(s) for s in args.symbols]
            print(json.dumps(results if len(results) > 1 else results[0], indent=2))

        elif args.command == "news":
            articles = get_company_news(args.symbol, args.days)
            articles = articles[: args.top]
            print(json.dumps(articles, indent=2))
            print(f"\n{len(articles)} article(s) for {args.symbol.upper()} (last {args.days} days)")

        elif args.command == "profile":
            print(json.dumps(get_company_profile(args.symbol), indent=2))

    except requests.HTTPError as e:
        print(f"ERROR: {e.response.status_code} {e.response.text}")
        sys.exit(1)
