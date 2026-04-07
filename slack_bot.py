"""
Slack Bot — Portfolio Copilot interface
Listens for DMs and @mentions via Socket Mode and routes them to agent.ask().
Maintains per-user conversation history for multi-turn context.

Usage:
    python slack_bot.py

Requires in .env:
    SLACK_BOT_TOKEN    — xoxb-... (Bot User OAuth Token)
    SLACK_APP_TOKEN    — xapp-... (App-Level Token with connections:write scope)
    SLACK_SIGNING_SECRET
"""

import os
import sys
import re
import logging
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

import agent

load_dotenv()

logging.basicConfig(level=logging.WARNING)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    print("ERROR: SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in .env")
    print("See workflows/slack_setup.md for setup instructions.")
    sys.exit(1)

app = App(token=SLACK_BOT_TOKEN)

# Per-user conversation history (in-memory; resets on bot restart)
_history: dict[str, list] = {}


CONFIRM_WORDS = {"confirm", "yes", "yeah", "yep", "ok", "okay"}
CANCEL_WORDS = {"cancel", "no", "nope", "abort", "stop"}


def _reply_async(client, channel: str, user_id: str, text: str):
    """Run agent in a background thread so Slack's 3s ack window is never hit."""
    def run():
        normalized = text.strip().lower()

        # Intercept confirm/cancel for pending orders
        if normalized in CONFIRM_WORDS and agent.get_pending_order(user_id):
            result = agent.execute_pending_order(user_id)
            client.chat_postMessage(channel=channel, text=result)
            return

        if normalized in CANCEL_WORDS and agent.get_pending_order(user_id):
            agent.clear_pending_order(user_id)
            client.chat_postMessage(channel=channel, text="Order cancelled.")
            return

        try:
            answer, updated = agent.ask(text, _history.get(user_id, []), user_id=user_id)
            _history[user_id] = updated[-20:]
            client.chat_postMessage(channel=channel, text=answer)
        except Exception as e:
            client.chat_postMessage(channel=channel, text=f"Sorry, something went wrong: {e}")

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

@app.event("message")
def handle_dm(event, client):
    """Respond to direct messages."""
    if event.get("bot_id") or event.get("subtype"):
        return
    user_id = event.get("user")
    channel = event.get("channel")
    text = event.get("text", "").strip()
    if not text or not user_id:
        return
    _reply_async(client, channel, user_id, text)


@app.event("app_mention")
def handle_mention(event, client):
    """Respond to @mentions in channels."""
    user_id = event.get("user")
    channel = event.get("channel")
    text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
    if not text:
        client.chat_postMessage(channel=channel, text="Yes? Ask me anything about your portfolio.")
        return
    _reply_async(client, channel, user_id, text)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting Portfolio Copilot Slack bot...")
    print("Press Ctrl+C to stop.\n")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
