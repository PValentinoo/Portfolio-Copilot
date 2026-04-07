"""
Finance Agent — AI layer
Connects OpenAI function calling to the Saxo Bank and Finnhub tools.
Runs as a CLI chat loop for testing; the same ask() function is reused by the Slack bot.

Usage:
    python agent.py
"""

import os
import re
import sys
import json
from openai import OpenAI
from dotenv import load_dotenv

# Add tools/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

import saxo_portfolio
import saxo_instruments
import saxo_prices
import saxo_orders
import saxo_news as saxo_news_tool
import finnhub as finnhub_tool
import web_search as web_search_tool

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-5.4-mini"

SYSTEM_PROMPT = """You are Portfolio Copilot, a personal investment assistant for a Saxo Bank account.
You have access to live portfolio data, stock prices, financial news, and the ability to place trades.

Guidelines:
- Always respond in the same language the user writes in. If they write in Danish, reply in Danish.
- Answer in clear, concise language. Use bullet points for lists.
- Always cite numbers with their currency.
- When showing price changes, include both absolute and percentage where possible.
- Clearly separate facts (from data) from any interpretation you add.
- If data is unavailable, say so — never fabricate numbers.
- Keep responses focused. Don't dump all available data unless asked.

Trading rules — follow these strictly:
- Each user message starts with [user_id:XYZ] — extract that value and pass it as user_id to propose_order.
- NEVER place a trade in a single step. Always call propose_order first.
- propose_order shows the user a summary and asks them to reply "confirm" to proceed.
- After calling propose_order, stop. Do not call any other tools. Wait for the user to confirm.
- If the user says "cancel" or does not confirm, do not execute the order.
- Only one pending order can exist at a time. If the user requests a new order while one is pending, propose the new one (it replaces the old).

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
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": (
                "Searches the web for recent news about a company, stock, or topic. "
                "Use this when get_news returns no results, especially for Danish or Nordic stocks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'Skjern Bank nyheder 2024' or 'Novo Nordisk earnings'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_order",
            "description": (
                "Proposes a buy or sell order. Resolves the instrument, fetches the current price, "
                "calculates estimated cost, and stores a pending order waiting for user confirmation. "
                "Always call this before any trade — never execute directly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'AAPL'"},
                    "quantity": {"type": "number", "description": "Number of shares/units to buy or sell"},
                    "direction": {"type": "string", "enum": ["Buy", "Sell"], "description": "Buy or Sell"},
                    "user_id": {"type": "string", "description": "Slack user ID, used to associate the pending order"},
                },
                "required": ["symbol", "quantity", "direction", "user_id"],
            },
        },
    },
]

# Saxo ExchangeId → Finnhub exchange suffix (for non-US stocks)
_EXCHANGE_MAP = {
    "CSE":  ":XCSE",   # Copenhagen
    "STO":  ":XSTO",   # Stockholm
    "HEX":  ":XHEL",   # Helsinki
    "OSE":  ":XOSL",   # Oslo
    "LSE":  ":XLON",   # London
    "EPA":  ":XPAR",   # Paris
    "ETR":  ":XETR",   # Frankfurt/XETRA
    "AMS":  ":XAMS",   # Amsterdam
}


def _resolve_instrument(query: str) -> dict | None:
    """Search Saxo for an instrument and return the best match dict."""
    results = saxo_instruments.search_instruments(query, top=5)
    if not results:
        return None
    for r in results:
        if r.get("Symbol", "").upper() == query.upper():
            return r
    return results[0]


def _finnhub_symbol(inst: dict, fallback_symbol: str) -> str:
    """Build a Finnhub-compatible ticker, adding exchange suffix for non-US stocks."""
    symbol = inst.get("Symbol") or fallback_symbol
    exchange_id = inst.get("ExchangeId", "")
    suffix = _EXCHANGE_MAP.get(exchange_id, "")
    return f"{symbol}{suffix}"


# ---------------------------------------------------------------------------
# Pending order store — keyed by Slack user_id
# ---------------------------------------------------------------------------

_pending_orders: dict[str, dict] = {}


def get_pending_order(user_id: str) -> dict | None:
    return _pending_orders.get(user_id)


def clear_pending_order(user_id: str):
    _pending_orders.pop(user_id, None)


def execute_pending_order(user_id: str) -> str:
    """Execute the stored pending order for a user. Returns a result message."""
    order = _pending_orders.pop(user_id, None)
    if not order:
        return "No pending order found."
    try:
        account_key = saxo_orders.get_account_key()
        result = saxo_orders.place_order(
            account_key=account_key,
            uic=order["uic"],
            asset_type=order["asset_type"],
            buy_sell=order["direction"],
            quantity=order["quantity"],
        )
        order_id = result.get("OrderId", "unknown")
        return (
            f"Order placed. *{order['direction']} {order['quantity']} x {order['symbol']}* "
            f"at market price.\nOrder ID: `{order_id}`"
        )
    except Exception as e:
        return f"Order failed: {e}"


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
            results = []
            for symbol in args["symbols"]:
                inst = _resolve_instrument(symbol)
                if inst:
                    ticker = _finnhub_symbol(inst, symbol)
                else:
                    ticker = symbol
                results.append(finnhub_tool.get_quote(ticker))
            return json.dumps(results)

        elif name == "get_news":
            symbol = args["symbol"]
            top = args.get("top", 5)
            # 1. Try Saxo news (best for Nordic/Danish stocks)
            try:
                inst = _resolve_instrument(symbol)
                if inst:
                    uic = inst["Identifier"]
                    asset_type = inst["AssetType"]
                    raw = saxo_news_tool.get_news_for_instrument(uic, asset_type, top=top)
                    if raw:
                        return json.dumps([saxo_news_tool.format_article(a) for a in raw])
            except Exception:
                pass
            # 2. Try Finnhub with exchange-aware ticker
            try:
                inst = _resolve_instrument(symbol)
                ticker = _finnhub_symbol(inst, symbol) if inst else symbol
                articles = finnhub_tool.get_company_news(ticker, days=args.get("days", 7))
                if articles:
                    return json.dumps(articles[:top])
            except Exception:
                pass
            # 3. Fall back to Tavily web search
            inst = _resolve_instrument(symbol)
            company_name = inst.get("Description", symbol) if inst else symbol
            results = web_search_tool.search(f"{company_name} news", max_results=top)
            return json.dumps(results)

        elif name == "search_news":
            results = web_search_tool.search(
                args["query"],
                max_results=args.get("max_results", 5),
            )
            return json.dumps(results)

        elif name == "get_company_profile":
            profile = finnhub_tool.get_company_profile(args["symbol"])
            return json.dumps(profile)

        elif name == "search_instrument":
            results = saxo_instruments.search_instruments(args["query"], top=5)
            formatted = [saxo_instruments.format_instrument(r) for r in results]
            return json.dumps(formatted)

        elif name == "propose_order":
            symbol = args["symbol"].upper()
            quantity = float(args["quantity"])
            direction = args["direction"]
            user_id = args.get("user_id", "default")

            # Resolve instrument on Saxo
            instruments = saxo_instruments.search_instruments(symbol, top=5)
            if not instruments:
                return json.dumps({"error": f"Instrument '{symbol}' not found on Saxo."})
            # Prefer exact symbol match
            match = next((i for i in instruments if i.get("Symbol", "").upper() == symbol), instruments[0])
            uic = match["Identifier"]
            asset_type = match["AssetType"]
            description = match.get("Description", symbol)
            currency = match.get("CurrencyCode", "")

            # Get current price from Saxo; fall back to Finnhub
            price = None
            try:
                raw = saxo_prices.get_quote(uic, asset_type)
                fmt = saxo_prices.format_quote(raw)
                price = fmt.get("LastTraded") or fmt.get("Ask") or fmt.get("Bid")
            except Exception:
                pass
            if not price:
                try:
                    quote = finnhub_tool.get_quote(symbol)
                    price = quote.get("c")  # current price
                except Exception:
                    pass

            # Store pending order
            _pending_orders[user_id] = {
                "symbol": symbol,
                "description": description,
                "uic": uic,
                "asset_type": asset_type,
                "direction": direction,
                "quantity": quantity,
                "currency": currency,
                "estimated_price": price,
            }

            estimated_cost = f"{price * quantity:,.2f} {currency}" if price else "unknown"
            price_str = f"{price:,.2f} {currency}" if price else "unknown"

            return json.dumps({
                "proposal": (
                    f"{direction} {quantity} x {description} ({symbol})\n"
                    f"Estimated price: {price_str}\n"
                    f"Estimated total: {estimated_cost}\n"
                    f"Order type: Market (Day)\n"
                    f"Reply *confirm* to place this order or *cancel* to abort."
                )
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Markdown normaliser — convert GPT output to Slack markdown
# ---------------------------------------------------------------------------

def _to_slack_markdown(text: str) -> str:
    # ## Headers → plain bold
    text = re.sub(r"^#{1,3}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    # **bold** → *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # __bold__ → *bold*
    text = re.sub(r"__(.+?)__", r"*\1*", text)
    return text


# ---------------------------------------------------------------------------
# Agent core — reusable by CLI and Slack bot
# ---------------------------------------------------------------------------

def ask(question: str, history: list = None, user_id: str = "default") -> tuple[str, list]:
    """
    Send a question to the agent and return (answer, updated_history).
    Pass history to maintain conversational context across turns.
    user_id is used to associate pending orders with the correct user.
    """
    # Inject user_id into the question context so propose_order can use it
    augmented = f"[user_id:{user_id}] {question}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": augmented})

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
            answer = _to_slack_markdown(msg.content)
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
