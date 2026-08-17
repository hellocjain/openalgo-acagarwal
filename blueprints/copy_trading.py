"""
Copy Trading REST API & Webhook Blueprint for OpenAlgo.
Provides child account management, multi-strategy routing, client profile inspection,
pre-market readiness health checks, 1-click emergency square-off, and external webhook signal replication.
"""

from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request, session

from database.copy_trading_db import (
    add_child_account,
    assign_strategy_to_account,
    bulk_assign_subscribers_to_strategy,
    create_strategy,
    delete_child_account,
    delete_client_strategy_mapping,
    delete_strategy,
    export_client_trade_logs_csv,
    get_account_strategies,
    get_all_child_accounts,
    get_all_strategies,
    get_child_account,
    get_copy_orders,
    get_master_switch,
    get_premarket_readiness_summary,
    get_strategy_by_id,
    get_strategy_subscribers_matrix,
    set_master_switch,
    toggle_child_account,
    toggle_client_strategy_mapping,
    update_child_account,
    update_client_strategy_mapping,
    update_strategy,
)
from services.copy_risk_service import (
    cancel_orders_by_account_id,
    emergency_squareoff_all_accounts,
    fetch_client_profile_details,
    refresh_all_child_accounts_telemetry,
    run_premarket_fire_drill,
    squareoff_by_account_id,
)
from services.copy_trading_service import (
    broadcast_copy_order,
    get_or_refresh_child_token,
    get_plain_english_feed,
)
from utils.logging import get_logger

logger = get_logger(__name__)

copy_trading_bp = Blueprint("copy_trading_bp", __name__, url_prefix="/api/copy-trading")


# =====================================================================
# Master Switch & Readiness Telemetry
# =====================================================================

@copy_trading_bp.route("/readiness", methods=["GET"])
def get_readiness():
    """Get pre-market readiness summary for the top health bar."""
    summary = get_premarket_readiness_summary()
    return jsonify({"status": "success", "data": summary})


@copy_trading_bp.route("/master-switch", methods=["POST"])
def toggle_master_switch():
    """Toggle global master copy trading switch."""
    data = request.get_json() or {}
    new_state = bool(data.get("active", True))
    res = set_master_switch(new_state)
    status_label = "ACTIVE" if res else "PAUSED"
    logger.info(f"[Copy Trading] Master Switch toggled to {status_label}")
    return jsonify({"status": "success", "master_switch_active": res, "message": f"Copy Trading is now {status_label}"})


@copy_trading_bp.route("/fire-drill", methods=["POST"])
def trigger_fire_drill():
    """Run zero-risk Pre-Market Fire Drill across all 100 accounts."""
    report = run_premarket_fire_drill()
    return jsonify(report)


@copy_trading_bp.route("/feed", methods=["GET"])
def get_feed():
    """Get latest plain-English signal execution feed cards."""
    feed = get_plain_english_feed()
    return jsonify({"status": "success", "feed": feed})


# =====================================================================
# Client Accounts CRUD & Inspection
# =====================================================================

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
            "master_switch_active": get_master_switch(),
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
        acc_dict = res.get("data", {})
        acc_dict["api_key"] = api_key
        acc_dict["api_secret"] = api_secret
        conn_ok, token, err = get_or_refresh_child_token(acc_dict)
        if conn_ok:
            res["message"] = "Account added and connected successfully!"
        else:
            res["message"] = f"Account added, but initial login ping failed: {err}"

    return jsonify(res)


@copy_trading_bp.route("/accounts/<int:account_id>/details", methods=["GET"])
def get_account_details(account_id: int):
    """Fetch complete live details for a single client to populate the Client Inspection Drawer."""
    res = fetch_client_profile_details(account_id)
    return jsonify(res)


@copy_trading_bp.route("/accounts/update/<int:account_id>", methods=["POST"])
def edit_account(account_id: int):
    """Update child trading account configuration."""
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
        multiplier=data.get("multiplier"),
        fixed_qty=data.get("fixed_qty"),
        max_lot_cap=data.get("max_lot_cap"),
        max_daily_loss=data.get("max_daily_loss"),
        is_active=data.get("is_active"),
    )
    return jsonify(res)


@copy_trading_bp.route("/accounts/toggle/<int:account_id>", methods=["POST"])
def toggle_account(account_id: int):
    """Toggle active status for a child trading account."""
    data = request.get_json() or {}
    is_active = data.get("is_active")
    res = toggle_child_account(account_id, is_active=is_active)
    return jsonify(res)


@copy_trading_bp.route("/accounts/delete/<int:account_id>", methods=["DELETE", "POST"])
def remove_account(account_id: int):
    """Delete a child account."""
    res = delete_child_account(account_id)
    return jsonify(res)


@copy_trading_bp.route("/accounts/<int:account_id>/squareoff", methods=["POST"])
def squareoff_client(account_id: int):
    """Emergency 1-click square-off for a single client."""
    res = squareoff_by_account_id(account_id)
    return jsonify(res)


@copy_trading_bp.route("/accounts/<int:account_id>/cancel-orders", methods=["POST"])
def cancel_client_orders(account_id: int):
    """1-click cancel all pending orders for a single client."""
    res = cancel_orders_by_account_id(account_id)
    return jsonify(res)


@copy_trading_bp.route("/accounts/<int:account_id>/order", methods=["POST"])
def place_client_order(account_id: int):
    """Place a direct order or smart order for a specific client account."""
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON payload"}), 400

    account = get_child_account(account_id, include_secrets=True)
    if not account:
        return jsonify({"status": "error", "message": "Child account not found"}), 404

    from services.copy_trading_service import execute_order_for_single_account
    result = execute_order_for_single_account(account, data)
    return jsonify(result)


@copy_trading_bp.route("/export/client/<int:account_id>", methods=["GET"])
def export_client_csv(account_id: int):
    """Download trade logs for a specific client as CSV."""
    csv_text = export_client_trade_logs_csv(account_id)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=client_{account_id}_trade_report.csv"},
    )


# =====================================================================
# Strategy Definition CRUD & Client Mappings
# =====================================================================

@copy_trading_bp.route("/strategies", methods=["GET"])
def list_strategies():
    """List all strategies with subscriber count and total strategy PnL."""
    strategies = get_all_strategies(include_subscribers=True)
    return jsonify({"status": "success", "strategies": strategies})


@copy_trading_bp.route("/strategies/add", methods=["POST"])
def add_strategy():
    """Create a new copy trading strategy definition."""
    data = request.get_json() or {}
    strategy_tag = data.get("strategy_tag")
    strategy_name = data.get("strategy_name")

    if not strategy_tag or not strategy_name:
        return jsonify({"status": "error", "message": "strategy_tag and strategy_name are required"}), 400

    res = create_strategy(
        strategy_tag=strategy_tag,
        strategy_name=strategy_name,
        segment=data.get("segment", "MCXFO"),
        timeframe=data.get("timeframe", "1m"),
        default_symbol=data.get("default_symbol", "CRUDEOIL"),
        description=data.get("description"),
        is_active=data.get("is_active", True),
    )
    return jsonify(res)


@copy_trading_bp.route("/strategies/update/<int:strategy_id>", methods=["POST"])
def edit_strategy(strategy_id: int):
    """Update strategy metadata."""
    data = request.get_json() or {}
    res = update_strategy(
        strategy_id=strategy_id,
        strategy_name=data.get("strategy_name"),
        segment=data.get("segment"),
        timeframe=data.get("timeframe"),
        default_symbol=data.get("default_symbol"),
        description=data.get("description"),
        is_active=data.get("is_active"),
    )
    return jsonify(res)


@copy_trading_bp.route("/strategies/delete/<int:strategy_id>", methods=["DELETE", "POST"])
def remove_strategy(strategy_id: int):
    """Delete a strategy and all its client mappings."""
    res = delete_strategy(strategy_id)
    return jsonify(res)


@copy_trading_bp.route("/accounts/<int:account_id>/assign-strategy", methods=["POST"])
def assign_strategy(account_id: int):
    """Assign a strategy to a client account with custom multiplier and risk bounds."""
    data = request.get_json() or {}
    strategy_id = data.get("strategy_id")
    if not strategy_id:
        return jsonify({"status": "error", "message": "strategy_id is required"}), 400

    multiplier = float(data.get("multiplier", 1.0))
    fixed_qty = int(data.get("fixed_qty", 0))
    max_daily_loss = float(data.get("max_daily_loss", 5000.0))

    res = assign_strategy_to_account(
        account_id=account_id,
        strategy_id=strategy_id,
        multiplier=multiplier,
        fixed_qty=fixed_qty,
        max_daily_loss=max_daily_loss,
        is_active=True,
    )
    return jsonify(res)


@copy_trading_bp.route("/mapping/update/<int:mapping_id>", methods=["POST"])
def edit_mapping(mapping_id: int):
    """Update mapping multiplier or loss limit."""
    data = request.get_json() or {}
    res = update_client_strategy_mapping(
        mapping_id=mapping_id,
        multiplier=data.get("multiplier"),
        fixed_qty=data.get("fixed_qty"),
        max_daily_loss=data.get("max_daily_loss"),
        is_active=data.get("is_active"),
    )
    return jsonify(res)


@copy_trading_bp.route("/mapping/toggle/<int:mapping_id>", methods=["POST"])
def toggle_mapping(mapping_id: int):
    """Toggle 1-click active status for a specific strategy on a client."""
    data = request.get_json() or {}
    res = toggle_client_strategy_mapping(mapping_id, is_active=data.get("is_active"))
    return jsonify(res)


@copy_trading_bp.route("/mapping/delete/<int:mapping_id>", methods=["DELETE", "POST"])
def remove_mapping(mapping_id: int):
    """Remove a strategy assignment from an account."""
    res = delete_client_strategy_mapping(mapping_id)
    return jsonify(res)


@copy_trading_bp.route("/strategies/<int:strategy_id>/subscribers", methods=["GET"])
def get_strategy_subscribers(strategy_id: int):
    """Retrieve full matrix of all accounts and their subscription state for this strategy."""
    matrix = get_strategy_subscribers_matrix(strategy_id)
    return jsonify({"status": "success", "subscribers": matrix})


@copy_trading_bp.route("/strategies/<int:strategy_id>/bulk-subscribers", methods=["POST"])
def bulk_update_strategy_subscribers(strategy_id: int):
    """Bulk update or assign clients subscribed to a strategy."""
    data = request.get_json(force=True, silent=True) or {}
    subscribers = data.get("subscribers", [])
    replace_all = data.get("replace_all", False)

    res = bulk_assign_subscribers_to_strategy(strategy_id, subscribers, replace_all=replace_all)
    return jsonify(res)


@copy_trading_bp.route("/telegram-test", methods=["POST"])
def test_telegram_alert():
    """Send a test message to verify Telegram bot setup."""
    import os
    import requests

    data = request.get_json(force=True, silent=True) or {}
    bot_token = data.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = data.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return jsonify({"status": "error", "message": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing"}), 400

    try:
        msg = (
            "🤖 <b>OpenAlgo Copy-Trading Telegram Test</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>Status:</b> Connected & Ready\n"
            "⚡ <b>Engine:</b> Institutional Multi-Account Router\n"
            "📈 <b>Broker:</b> AC Agarwal Symphony XTS\n"
            f"🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
        if resp.status_code == 200:
            return jsonify({"status": "success", "message": "Test message sent to Telegram successfully!"})
        else:
            return jsonify({"status": "error", "message": f"Telegram API error: {resp.text}"}), resp.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =====================================================================
# Emergency & Synchronization Endpoints
# =====================================================================

@copy_trading_bp.route("/squareoff-all", methods=["POST"])
def emergency_squareoff():
    """1-Click Emergency Square-Off across ALL 100+ child accounts."""
    res = emergency_squareoff_all_accounts()
    return jsonify(res)


@copy_trading_bp.route("/sync", methods=["POST"])
def sync_telemetry():
    """Refresh funds and PnL telemetry across all accounts."""
    results = refresh_all_child_accounts_telemetry()
    return jsonify({"status": "success", "results": results, "total_synced": len(results)})


@copy_trading_bp.route("/orders", methods=["GET"])
def list_copy_orders():
    """List recent copy orders with execution status and latency metrics."""
    limit = int(request.args.get("limit", 100))
    account_id = request.args.get("account_id", type=int)
    orders = get_copy_orders(limit=limit, account_id=account_id)
    return jsonify({"status": "success", "orders": orders})


# =====================================================================
# Webhook Signal Ingestion (TradingView / Python)
# =====================================================================

def is_authenticated_webhook(data: dict) -> bool:
    """Verify request via active session, X-API-Key header, or payload apikey."""
    try:
        from utils.session import is_session_valid
        if is_session_valid():
            return True
    except Exception:
        pass

    api_key = (
        data.get("apikey")
        or request.headers.get("X-API-Key")
        or request.headers.get("Authorization")
    )
    if api_key:
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()
        try:
            from database.auth_db import verify_api_key
            user_id = verify_api_key(api_key)
            if user_id:
                return True
        except Exception:
            pass

    try:
        from database.auth_db import get_first_available_api_key
        if not get_first_available_api_key():
            return True  # Fresh instance before key generation
    except Exception:
        return True

    return False


@copy_trading_bp.route("/webhook", methods=["POST"])
def copy_webhook():
    """
    Replicate external trading signal across all mapped child accounts.
    Accepts standard OpenAlgo JSON payload + optional 'strategy' tag.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON payload"}), 400

    # 1. Security & Authentication Check
    if not is_authenticated_webhook(data):
        return jsonify({"status": "error", "message": "Unauthorized: Invalid or missing API key"}), 401

    # 2. Strict Input Validation
    symbol = (data.get("symbol") or "").strip().upper()
    action = (data.get("action") or "").strip().upper()
    raw_qty = data.get("quantity")

    if not symbol or not action or raw_qty is None:
        return jsonify({"status": "error", "message": "symbol, action, and quantity are required"}), 400

    if action not in ["BUY", "SELL"]:
        return jsonify({"status": "error", "message": "action must be BUY or SELL"}), 400

    try:
        quantity = int(raw_qty)
        if quantity <= 0:
            return jsonify({"status": "error", "message": "quantity must be greater than zero"}), 400
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "quantity must be a positive integer"}), 400

    data["symbol"] = symbol
    data["action"] = action
    data["quantity"] = quantity

    # Sanitize pricetype & product
    pricetype = (data.get("pricetype") or "MARKET").strip().upper()
    if pricetype not in ["MARKET", "LIMIT", "SL", "SL-M"]:
        pricetype = "MARKET"
    data["pricetype"] = pricetype

    product = (data.get("product") or "MIS").strip().upper()
    if product not in ["MIS", "NRML", "CNC"]:
        product = "MIS"
    data["product"] = product

    # Sanitize strategy tag if provided
    if data.get("strategy"):
        data["strategy"] = str(data["strategy"]).strip().upper().replace(" ", "_")

    # Broadcast signal in parallel with dynamic strategy routing
    result = broadcast_copy_order(data)
    return jsonify(result)
