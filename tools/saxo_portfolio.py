"""
Saxo Bank Portfolio Tool
Fetches account info, balances, and positions from the Saxo Bank OpenAPI.
Uses a direct access token from .env (no OAuth flow needed for SIM testing).

Usage:
    python tools/saxo_portfolio.py
    python tools/saxo_portfolio.py --section balances
    python tools/saxo_portfolio.py --section positions
    python tools/saxo_portfolio.py --section accounts
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


def get_headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


def saxo_get(path: str, params: dict = None) -> dict:
    url = f"{BASE_URL}{path}"
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()


def get_accounts() -> list:
    data = saxo_get("/port/v1/accounts/me")
    return data.get("Data", [])


def get_balances(client_key: str) -> dict:
    return saxo_get("/port/v1/balances", params={"ClientKey": client_key})


def get_positions(client_key: str) -> list:
    data = saxo_get("/port/v1/positions/me", params={"ClientKey": client_key})
    return data.get("Data", [])


def get_client_info() -> dict:
    return saxo_get("/port/v1/clients/me")


def print_section(title: str, data):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2))


def run(section: str = "all"):
    if not TOKEN:
        print("ERROR: SAXO_ACCESS_TOKEN is not set in .env")
        sys.exit(1)

    print(f"Environment : {ENVIRONMENT.upper()}")
    print(f"Base URL    : {BASE_URL}")

    # Get client info (needed for ClientKey)
    try:
        client = get_client_info()
    except requests.HTTPError as e:
        print(f"\nERROR fetching client info: {e.response.status_code} {e.response.text}")
        sys.exit(1)

    client_key = client.get("ClientKey")
    print(f"Client Key  : {client_key}")
    print(f"Client Name : {client.get('Name')}")

    if section in ("all", "accounts"):
        try:
            accounts = get_accounts()
            print_section("ACCOUNTS", accounts)
        except requests.HTTPError as e:
            print(f"\nERROR fetching accounts: {e.response.status_code} {e.response.text}")

    if section in ("all", "balances"):
        try:
            balances = get_balances(client_key)
            print_section("BALANCES", balances)
        except requests.HTTPError as e:
            print(f"\nERROR fetching balances: {e.response.status_code} {e.response.text}")

    if section in ("all", "positions"):
        try:
            positions = get_positions(client_key)
            print_section(f"POSITIONS ({len(positions)} open)", positions)
        except requests.HTTPError as e:
            print(f"\nERROR fetching positions: {e.response.status_code} {e.response.text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Saxo Bank portfolio data")
    parser.add_argument(
        "--section",
        choices=["all", "accounts", "balances", "positions"],
        default="all",
        help="Which section to fetch (default: all)",
    )
    args = parser.parse_args()
    run(args.section)
