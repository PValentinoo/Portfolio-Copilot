"""
Finance Agent — AI layer
Connects OpenAI function calling to the Saxo Bank and Finnhub tools.
Runs as a CLI chat loop for testing; the same ask() function is reused by the Slack bot.

Usage:
    python agent.py
"""

import os
import sys
import json
from openai import OpenAI
from dotenv import load_dotenv

# Add tools/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

import saxo_portfolio
import saxo_instruments
import finnhub as finnhub_tool

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o"

SYSTEM_PROMPT = """You are Portfolio Copilot, a personal investment assistant for a Saxo Bank account.
You have access to live portfolio data, stock prices, and financial news.

Guidelines:
- Answer in clear, concise language. Use bullet points for lists.
- Always cite numbers with their currency.
- When showing price changes, include both absolute and percentage where possible.
- Clearly separate facts (from data) from any interpretation you add.
- If data is unavailable, say so — never fabricate numbers.
- Keep responses focused. Don't dump all available data unless asked.

Formatting — responses are displayed in Slack, so use Slack markdown only:
- Bold: *text* (single asterisk, NOT double asterisks)
- Italic: _text_
- Bullet points: - or •
- Never use ## headers or **double asterisk bold**
- Never use markdown tables
"""

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling schema)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_overview",
            "description": "Returns account balances, total portfolio value, cash, margin, and open position count.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_positions",
            "description": "Returns all open positions in the portfolio with instrument details.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price",
            "description": "Gets the current market price for one or more stock symbols.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ticker symbols, e.g. ['AAPL', 'TSLA']",
                    }
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Gets recent news headlines and summaries for a stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'AAPL'"},
                    "days": {
                        "type": "integer",
                        "description": "How many days back to fetch news (default 7)",
                        "default": 7,
                    },
                    "top": {
                        "type": "integer",
                        "description": "Maximum number of articles to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_profile",
            "description": "Gets company background info: sector, country, market cap, exchange.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'NVO'"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_instrument",
            "description": "Searches for a stock/ETF/fund by name or ticker on Saxo Bank. Returns Uic and AssetType needed for other Saxo calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Company name or ticker to search for"}
                },
                "required": ["query"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

_client_key_cache: str = None

def _get_client_key() -> str:
    global _client_key_cache
    if not _client_key_cache:
        _client_key_cache = saxo_portfolio.get_client_info()["ClientKey"]
    return _client_key_cache


def execute_tool(name: str, args: dict) -> str:
    try:
        if name == "get_portfolio_overview":
            client_key = _get_client_key()
            balances = saxo_portfolio.get_balances(client_key)
            return json.dumps({
                "TotalValue": balances.get("TotalValue"),
                "CashBalance": balances.get("CashBalance"),
                "Currency": balances.get("Currency"),
                "OpenPositionsCount": balances.get("OpenPositionsCount"),
                "UnrealizedPnL": balances.get("UnrealizedMarginProfitLoss"),
                "MarginUtilizationPct": balances.get("MarginUtilizationPct"),
            })

        elif name == "get_positions":
            client_key = _get_client_key()
            positions = saxo_portfolio.get_positions(client_key)
            if not positions:
                return json.dumps({"message": "No open positions."})
            return json.dumps(positions)

        elif name == "get_price":
            symbols = args["symbols"]
            results = [finnhub_tool.get_quote(s) for s in symbols]
            return json.dumps(results)

        elif name == "get_news":
            articles = finnhub_tool.get_company_news(
                args["symbol"],
                days=args.get("days", 7),
            )
            return json.dumps(articles[: args.get("top", 5)])

        elif name == "get_company_profile":
            profile = finnhub_tool.get_company_profile(args["symbol"])
            return json.dumps(profile)

        elif name == "search_instrument":
            results = saxo_instruments.search_instruments(args["query"], top=5)
            formatted = [saxo_instruments.format_instrument(r) for r in results]
            return json.dumps(formatted)

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Agent core — reusable by CLI and Slack bot
# ---------------------------------------------------------------------------

def ask(question: str, history: list = None) -> tuple[str, list]:
    """
    Send a question to the agent and return (answer, updated_history).
    Pass history to maintain conversational context across turns.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    # Agentic loop — keep going until no more tool calls
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # No tool calls → final answer
        if not msg.tool_calls:
            answer = msg.content
            messages.append({"role": "assistant", "content": answer})
            # Return history without the system prompt
            return answer, messages[1:]

        # Execute all tool calls
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })


# ---------------------------------------------------------------------------
# CLI chat loop
# ---------------------------------------------------------------------------

def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set in .env")
        sys.exit(1)

    print("Portfolio Copilot ready. Type your question or 'quit' to exit.\n")
    history = []

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        try:
            answer, history = ask(question, history)
            print(f"\nAgent: {answer}\n")
        except Exception as e:
            print(f"\nERROR: {e}\n")


if __name__ == "__main__":
    main()
