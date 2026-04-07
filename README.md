# Portfolio Copilot

An AI-powered investment assistant that connects to your Saxo Bank account and lets you manage your portfolio through a Slack chat interface. Ask questions in natural language, get live portfolio data, and place trades — all from Slack. Supports Danish and English.

---

## What it can do

- View your portfolio value, positions, and balances
- Look up live stock prices (US, Danish, and Nordic stocks)
- Fetch recent news for any stock — with a fallback to web search for smaller Danish stocks
- Place market orders with a mandatory two-step confirmation
- Answer questions in Danish or English

---

## Architecture

The project follows the WAT framework: **Workflows, Agents, Tools**.

```
Slack
  ↓
slack_bot.py        — receives messages, handles order confirmation
  ↓
agent.py            — AI layer (OpenAI function calling)
  ↓
tools/              — deterministic Python scripts
  ├── saxo_portfolio.py   — balances, positions, account info
  ├── saxo_instruments.py — instrument search (resolve name/ticker → Uic)
  ├── saxo_prices.py      — live prices via Saxo API
  ├── saxo_orders.py      — place market orders
  ├── saxo_news.py        — news via Saxo News API
  ├── finnhub.py          — prices and news fallback (Finnhub API)
  └── web_search.py       — web search fallback (Tavily API)
```

**Why this separation matters:** each tool is a deterministic Python script. The AI agent handles reasoning and orchestration only — it never executes trades or data fetches directly. This keeps the system reliable and auditable.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/PValentinoo/Portfolio-Copilot.git
cd Portfolio-Copilot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the root directory:

```env
# Saxo Bank
SAXO_ACCESS_TOKEN=your_token_here
SAXO_ENVIRONMENT=sim   # or "live" for real trading

# OpenAI
OPENAI_API_KEY=your_key_here

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=your_secret_here

# News & search
FINNHUB_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

See `workflows/slack_setup.md` for step-by-step Slack app configuration.

### 4. Start the bot

```bash
python slack_bot.py
```

Or test the agent directly in the terminal without Slack:

```bash
python agent.py
```

---

## How trading works

Trading uses a mandatory two-step confirmation flow — the AI cannot place an order in a single step.

1. You: `buy 10 shares of Apple`
2. Bot shows a proposal:
   ```
   Buy 10 x Apple Inc. (AAPL)
   Estimated price: 189.50 USD
   Estimated total: 1,895.00 USD
   Order type: Market (Day)
   Reply confirm to place this order or cancel to abort.
   ```
3. You: `confirm` → order is placed via Saxo API
4. You: `cancel` → order is discarded

The confirmation is handled deterministically in `slack_bot.py` — not by the AI — so the model cannot trigger execution on its own.

---

## News sources

News is fetched using a three-tier fallback, which ensures coverage for small Danish and Nordic stocks:

1. **Saxo News API** — best for Nordic stocks, resolves by instrument Uic
2. **Finnhub** — fallback with exchange-aware tickers (e.g. `SKJE:XCSE` for Copenhagen)
3. **Tavily web search** — searches the live web; works for any company in any language

---

## Example questions

```
How is my portfolio doing today?
What are my biggest winners and losers?
What is the price of Novo Nordisk?
What news is affecting Skjern Bank?
Buy 5 shares of Apple
Hvad er min portefølje værd?
Hvilke aktier klarer sig bedst i dag?
```

---

## Project structure

```
agent.py              — AI agent core, tool definitions, order logic
slack_bot.py          — Slack bot, event handlers, confirm/cancel flow
tools/                — individual execution scripts
workflows/            — setup guides and SOPs
.env                  — API keys (never committed)
requirements.txt      — Python dependencies
```
