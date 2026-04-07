"""
Web Search Tool — Tavily
General-purpose web search for news and company information.
Useful for stocks with limited coverage on Finnhub/Saxo (e.g. small Danish/Nordic stocks).

Requires: TAVILY_API_KEY in .env (https://tavily.com)

Usage:
    python tools/web_search.py "Skjern Bank nyheder"
    python tools/web_search.py "Novo Nordisk earnings 2024" --max-results 3
"""

import os
import sys
import json
import argparse
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client() -> TavilyClient:
    global _client
    if not _client:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY is not set in .env")
        _client = TavilyClient(api_key=api_key)
    return _client


def search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web for a query. Returns a list of results with title, url, and content snippet.
    """
    client = _get_client()
    response = client.search(query, search_depth="basic", max_results=max_results)
    results = []
    for r in response.get("results", []):
        results.append({
            "Title": r.get("title"),
            "URL": r.get("url"),
            "Summary": r.get("content", "")[:400],
            "Score": round(r.get("score", 0), 3),
        })
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tavily web search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--max-results", type=int, default=5, help="Max results (default: 5)")
    args = parser.parse_args()

    try:
        results = search(args.query, args.max_results)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\n{len(results)} result(s) for: {args.query}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
