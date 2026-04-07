"""
Saxo Bank Order Tool
Places market orders via the Saxo Bank OpenAPI.

Usage:
    from tools.saxo_orders import get_account_key, place_order
"""

import os
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


def get_account_key() -> str:
    """Returns the first account key for the authenticated user."""
    response = requests.get(f"{BASE_URL}/port/v1/accounts/me", headers=get_headers())
    response.raise_for_status()
    accounts = response.json().get("Data", [])
    if not accounts:
        raise ValueError("No accounts found")
    return accounts[0]["AccountKey"]


def place_order(account_key: str, uic: int, asset_type: str, buy_sell: str, quantity: float) -> dict:
    """
    Place a market day order.

    Args:
        account_key: Saxo account key
        uic:         Instrument identifier (from saxo_instruments)
        asset_type:  e.g. "Stock", "Etf"
        buy_sell:    "Buy" or "Sell"
        quantity:    Number of units

    Returns:
        Saxo order response dict (contains OrderId on success)
    """
    body = {
        "AccountKey": account_key,
        "AssetType": asset_type,
        "BuySell": buy_sell,
        "Amount": quantity,
        "Uic": uic,
        "OrderType": "Market",
        "OrderDuration": {"DurationType": "DayOrder"},
        "ManualOrder": False,
    }
    response = requests.post(
        f"{BASE_URL}/trade/v2/orders",
        headers=get_headers(),
        json=body,
    )
    response.raise_for_status()
    return response.json()
