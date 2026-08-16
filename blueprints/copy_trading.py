"""
Copy Trading REST API & Webhook Blueprint for OpenAlgo.
Provides child account management, instant ping credential validation,
telemetry synchronization, 1-click emergency square-off, and external webhook signal replication.
"""

from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, request, session

from database.copy_trading_db import (
    add_child_account,
    delete_child_account,
    get_all_child_accounts,
    get_child_account,
    get_copy_orders,
    toggle_child_account,
    update_child_account,
)
from services.copy_risk_service import (
    emergency_squareoff_all_accounts,
    refresh_all_child_accounts_telemetry,
)
from services.copy_trading_service import (
    broadcast_copy_order,
    get_or_refresh_child_token,
)
from utils.logging import get_logger

logger = get_logger(__name__)

copy_trading_bp = Blueprint("copy_trading_bp", __name__, url_prefix="/api/copy-trading")


@copy_trading_bp.route("/accounts", methods=["GET"])
def list_accounts():
    """List all child accounts with aggregated summary telemetry."""
    accounts = get_all_child_accounts(active_only=False, include_secrets=False)
    total_accounts = len(accounts)
    active_accounts = sum(1 for a in accounts if a.get("is_active"))
    total_funds = sum(float(a.get("last_funds", 0.0) or 0.0) for a in accounts)
    total_pnl = sum(float(a.get("last_pnl", 0.0) or 0.0) for a in accounts)

    return jsonify({
        "status": "success",
        "summary": {
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "total_funds": round(total_funds, 2),
            "total_pnl": round(total_pnl, 2),
        },
        "accounts": accounts,
    })


@copy_trading_bp.route("/accounts/add", methods=["POST"])
def create_account():
    """Add a new child trading account with instant ping validation."""
    data = request.get_json() or {}
    account_name = data.get("account_name")
    client_code = data.get("client_code")
    api_key = data.get("api_key")
    api_secret = data.get("api_secret")

    if not account_name or not client_code or not api_key or not api_secret:
        return jsonify({"status": "error", "message": "account_name, client_code, api_key, and api_secret are required"}), 400

    api_key_market = data.get("api_key_market") or api_key
    api_secret_market = data.get("api_secret_market") or api_secret
    sizing_mode = data.get("sizing_mode", "MULTIPLIER")
    multiplier = float(data.get("multiplier", 1.0))
    fixed_qty = int(data.get("fixed_qty", 0))
    max_lot_cap = int(data.get("max_lot_cap", 50))
    max_daily_loss = float(data.get("max_daily_loss", 5000.0))

    # Add account to database
    res = add_child_account(
        account_name=account_name,
        client_code=client_code,
        api_key=api_key,
        api_secret=api_secret,
        api_key_market=api_key_market,
        api_secret_market=api_secret_market,
        sizing_mode=sizing_mode,
        multiplier=multiplier,
        fixed_qty=fixed_qty,
        max_lot_cap=max_lot_cap,
        max_daily_loss=max_daily_loss,
    )

    if res.get("status") == "success":
        # Test connection immediately
        acc_dict = res.get("data", {})
        acc_dict["api_key"] = api_key
        acc_dict["api_secret"] = api_secret
        conn_ok, token, err = get_or_refresh_child_token(acc_dict)
        if conn_ok:
            res["message"] = "Account added and connected successfully!"
        else:
            res["message"] = f"Account added, but connection test failed: {err}"

    return jsonify(res)


@copy_trading_bp.route("/accounts/update/<int:account_id>", methods=["POST"])
def edit_account(account_id: int):
    """Update child account settings."""
    data = request.get_json() or {}
    res = update_child_account(
        account_id=account_id,
        account_name=data.get("account_name"),
        client_code=data.get("client_code"),
        api_key=data.get("api_key"),
        api_secret=data.get("api_secret"),
        api_key_market=data.get("api_key_market"),
        api_secret_market=data.get("api_secret_market"),
        sizing_mode=data.get("sizing_mode"),
        multiplier=float(data["multiplier"]) if "multiplier" in data else None,
        fixed_qty=int(data["fixed_qty"]) if "fixed_qty" in data else None,
        max_lot_cap=int(data["max_lot_cap"]) if "max_lot_cap" in data else None,
        max_daily_loss=float(data["max_daily_loss"]) if "max_daily_loss" in data else None,
        is_active=data.get("is_active"),
    )
    return jsonify(res)


@copy_trading_bp.route("/accounts/toggle/<int:account_id>", methods=["POST"])
def toggle_account(account_id: int):
    """Toggle active status for a child account."""
    data = request.get_json() or {}
    is_active = data.get("is_active")
    res = toggle_child_account(account_id, is_active=is_active)
    return jsonify(res)


@copy_trading_bp.route("/accounts/delete/<int:account_id>", methods=["DELETE", "POST"])
def remove_account(account_id: int):
    """Delete a child trading account."""
    res = delete_child_account(account_id)
    return jsonify(res)


@copy_trading_bp.route("/accounts/sync", methods=["POST"])
def sync_telemetry():
    """Trigger parallel refresh of balances and P&L for all child accounts."""
    results = refresh_all_child_accounts_telemetry()
    return jsonify({
        "status": "success",
        "message": f"Synced telemetry for {len(results)} accounts",
        "results": results,
    })


@copy_trading_bp.route("/squareoff-all", methods=["POST"])
def squareoff_all():
    """1-Click Emergency Square-Off: Closes all positions across all active child accounts."""
    logger.warning("[API] Received Emergency Square-Off All trigger!")
    res = emergency_squareoff_all_accounts()
    return jsonify(res)


@copy_trading_bp.route("/orders", methods=["GET"])
def list_copy_orders():
    """Retrieve recent copy-trade execution logs."""
    limit = int(request.args.get("limit", 100))
    orders = get_copy_orders(limit=limit)
    return jsonify({"status": "success", "orders": orders})


@copy_trading_bp.route("/webhook", methods=["POST"])
def receive_copy_webhook():
    """
    Copy Trading Signal Webhook Listener.
    Receives alerts from TradingView, Python strategies, or Chartink and replicates
    orders concurrently to all active AC Agarwal child accounts.
    """
    order_data = request.get_json() or {}
    symbol = order_data.get("symbol")
    action = order_data.get("action")
    exchange = order_data.get("exchange", "NSEFO")

    if not symbol or not action:
        return jsonify({"status": "error", "message": "symbol and action are mandatory fields"}), 400

    master_order_id = order_data.get("orderid") or f"WB_{int(datetime.utcnow().timestamp())}"
    logger.info(f"[Copy Webhook] Received trade signal: {symbol} ({action}) on {exchange}")

    broadcast_result = broadcast_copy_order(order_data, master_order_id=master_order_id)
    return jsonify(broadcast_result)
