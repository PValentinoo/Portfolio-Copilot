# Workflow: Portfolio Copilot — Slack App Setup

## Objective
Create a Slack app and connect it to the Portfolio Copilot so you can chat with your portfolio in Slack.

## Required Inputs
- A Slack workspace where you have permission to add apps
- The three tokens/secrets below (collected during setup)

## Steps

### 1. Create the Slack App

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. Name it `Portfolio Copilot` and select your workspace
4. Click **Create App**

---

### 2. Enable Socket Mode

Socket Mode lets the bot connect without a public URL (ideal for local/personal use).

1. In the left sidebar, click **Socket Mode**
2. Toggle **Enable Socket Mode** on
3. You'll be prompted to create an App-Level Token:
   - Name it `socket-token`
   - Add the scope: `connections:write`
   - Click **Generate**
4. Copy the token (starts with `xapp-`) → paste into `.env` as `SLACK_APP_TOKEN`

---

### 3. Add Bot Scopes

1. In the sidebar, go to **OAuth & Permissions**
2. Scroll to **Scopes → Bot Token Scopes**
3. Add the following scopes:
   - `app_mentions:read` — receive @mentions
   - `chat:write` — send messages
   - `im:history` — read DM history
   - `im:read` — receive DMs
   - `im:write` — open DM conversations

---

### 4. Enable Events

1. In the sidebar, go to **Event Subscriptions**
2. Toggle **Enable Events** on
3. Under **Subscribe to bot events**, add:
   - `message.im` — DMs sent to the bot
   - `app_mention` — @mentions in channels
4. Click **Save Changes**

---

### 5. Install the App

1. In the sidebar, go to **OAuth & Permissions**
2. Click **Install to Workspace** → **Allow**
3. Copy the **Bot User OAuth Token** (starts with `xoxb-`) → paste into `.env` as `SLACK_BOT_TOKEN`

---

### 6. Copy the Signing Secret

1. In the sidebar, go to **Basic Information**
2. Scroll to **App Credentials**
3. Copy the **Signing Secret** → paste into `.env` as `SLACK_SIGNING_SECRET`

---

### 7. Start the Bot

```bash
python slack_bot.py
```

You should see:
```
Starting Portfolio Copilot Slack bot...
⚡️ Bolt app is running!
```

---

### 8. Test It

In Slack:
- Open a DM with your Portfolio Copilot bot and send: `How is my portfolio doing?`
- Or in any channel where the bot is added: `@Portfolio Copilot What is the price of Apple?`

---

## Credentials Summary

| Variable | Where to find it | Format |
|---|---|---|
| `SLACK_BOT_TOKEN` | OAuth & Permissions → Bot User OAuth Token | `xoxb-...` |
| `SLACK_APP_TOKEN` | Socket Mode → App-Level Token | `xapp-...` |
| `SLACK_SIGNING_SECRET` | Basic Information → App Credentials | hex string |

## Edge Cases

- **Bot doesn't respond to DMs**: Make sure `message.im` event is subscribed and the app is reinstalled after adding scopes.
- **Bot responds to its own messages (loop)**: The bot filters `bot_id` events — if you see a loop, check that the bot token is a Bot token (`xoxb-`), not a user token.
- **History grows too large**: History is capped at 20 messages per user. Restart the bot to clear all history.
- **Token expired**: Saxo SIM tokens expire. Regenerate at https://www.developer.saxo/openapi/appmanagement and update `SAXO_ACCESS_TOKEN` in `.env`.
