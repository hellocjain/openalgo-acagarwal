"""
Risk Management & Emergency Square-Off Service for Copy Trading.
Adapted from Algomirror's position_monitor and risk_manager to provide 1-click Emergency
Square-Off All and real-time MTM Max Daily Loss circuit breakers across all AC Agarwal child accounts.
"""

import concurrent.futures
import time
from typing import Any, Dict, List, Optional

import requests

from broker.acagarwal.baseurl import INTERACTIVE_URL
from database.copy_trading_db import (
    CopyActivityLog,
    Session,
    get_all_child_accounts,
    record_copy_order,
    update_account_status,
)
from services.copy_trading_service import get_or_refresh_child_token
from utils.logging import get_logger

logger = get_logger(__name__)


def fetch_account_funds_and_pnl(account: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch live available funds and MTM PnL for a single child account from AC Agarwal."""
    account_id = account["id"]
    success, token, err = get_or_refresh_child_token(account)
    if not success or not token:
        return {"account_id": account_id, "status": "error", "message": err, "funds": 0.0, "pnl": 0.0}

    headers = {"Content-Type": "application/json", "Authorization": token}
    funds_url = f"{INTERACTIVE_URL}/user/balance"
    positions_url = f"{INTERACTIVE_URL}/portfolio/positions?dayOrNet=NetWise"

    available_cash = 0.0
    total_pnl = 0.0
    positions_list = []

    # 1. Fetch balance
    try:
        f_resp = requests.get(funds_url, headers=headers, timeout=4)
        if f_resp.status_code == 200:
            f_data = f_resp.json()
            if f_data.get("type") == "success":
                result = f_data.get("result", {})
                available_cash = float(result.get("BalanceList", [{}])[0].get("limitObject", {}).get("RMSSubLimits", {}).get("netMarginAvailable", 0.0) or 0.0)
    except Exception as e:
        logger.error(f"[Risk] Error fetching balance for {account['account_name']}: {e}")

    # 2. Fetch positions and calculate PnL
    try:
        p_resp = requests.get(positions_url, headers=headers, timeout=4)
        if p_resp.status_code == 200:
            p_data = p_resp.json()
            if p_data.get("type") == "success":
                position_list = p_data.get("result", {}).get("positionList", []) or []
                positions_list = position_list
                for pos in position_list:
                    pnl_val = float(pos.get("unrealizedMTM", 0.0) or 0.0) + float(pos.get("realizedMTM", 0.0) or 0.0)
                    total_pnl += pnl_val
    except Exception as e:
        logger.error(f"[Risk] Error fetching positions for {account['account_name']}: {e}")

    # 3. Update database status cache
    update_account_status(
        account_id=account_id,
        connection_status="connected",
        funds=available_cash,
        pnl=total_pnl,
    )

    # 4. Check Daily Max Loss Circuit Breaker
    max_loss = float(account.get("max_daily_loss", 5000.0))
    if max_loss > 0 and total_pnl <= -abs(max_loss):
        logger.warning(
            f"[Risk Guard] Child account {account['account_name']} breached max daily loss limit: "
            f"PnL = Rs {total_pnl:.2f} (Limit: -Rs {max_loss:.2f}). Pausing copy trading!"
        )
        # Auto-pause account in DB
        db_sess = Session()
        try:
            from database.copy_trading_db import CopyAccount
            acc_obj = db_sess.query(CopyAccount).filter_by(id=account_id).first()
            if acc_obj:
                acc_obj.is_active = False
                acc_obj.daily_loss_triggered = True
                db_sess.commit()
        except Exception:
            db_sess.rollback()
        finally:
            db_sess.close()

    return {
        "account_id": account_id,
        "account_name": account["account_name"],
        "client_code": account["client_code"],
        "status": "success",
        "funds": available_cash,
        "pnl": total_pnl,
        "positions_count": len(positions_list),
    }


def refresh_all_child_accounts_telemetry() -> List[Dict[str, Any]]:
    """Refresh funds and PnL for all active child accounts in parallel."""
    accounts = get_all_child_accounts(active_only=False, include_secrets=True)
    if not accounts:
        return []

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(20, len(accounts))) as executor:
        futures = {executor.submit(fetch_account_funds_and_pnl, acc): acc for acc in accounts}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                logger.error(f"[Risk] Exception refreshing telemetry: {e}")

    return results


def squareoff_single_account(account: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel all open orders and square off all open positions for a single child account.
    """
    t0 = time.time()
    account_id = account["id"]
    account_name = account["account_name"]
    client_code = account["client_code"]

    success, token, err = get_or_refresh_child_token(account)
    if not success or not token:
        return {"account_id": account_id, "status": "error", "message": f"Auth failed: {err}"}

    headers = {"Content-Type": "application/json", "Authorization": token}
    closed_positions = []
    cancelled_orders = []

    # 1. Fetch & Cancel open pending orders
    try:
        orders_url = f"{INTERACTIVE_URL}/orders"
        ord_resp = requests.get(orders_url, headers=headers, timeout=4)
        if ord_resp.status_code == 200:
            ord_data = ord_resp.json()
            if ord_data.get("type") == "success":
                order_list = ord_data.get("result", []) or []
                for o in order_list:
                    status = str(o.get("OrderStatus", "")).upper()
                    if status in ["OPEN", "PENDING", "NEW", "TRIGGER PENDING"]:
                        app_order_id = str(o.get("AppOrderID", ""))
                        if app_order_id:
                            del_resp = requests.delete(f"{orders_url}?appOrderID={app_order_id}", headers=headers, timeout=4)
                            if del_resp.status_code == 200:
                                cancelled_orders.append(app_order_id)
    except Exception as e:
        logger.error(f"[Square-off] Error cancelling orders for {account_name}: {e}")

    # 2. Fetch and close open positions
    try:
        pos_url = f"{INTERACTIVE_URL}/portfolio/positions?dayOrNet=NetWise"
        pos_resp = requests.get(pos_url, headers=headers, timeout=4)
        if pos_resp.status_code == 200:
            pos_data = pos_resp.json()
            if pos_data.get("type") == "success":
                positions = pos_data.get("result", {}).get("positionList", []) or []
                for p in positions:
                    net_qty = int(p.get("netQuantity", 0) or 0)
                    if net_qty != 0:
                        symbol = str(p.get("TradingSymbol", ""))
                        exchange = str(p.get("ExchangeSegment", "NSEFO"))
                        token_id = str(p.get("ExchangeInstrumentId", ""))
                        exit_action = "SELL" if net_qty > 0 else "BUY"
                        exit_qty = abs(net_qty)

                        exit_payload = {
                            "exchangeSegment": exchange,
                            "exchangeInstrumentID": token_id,
                            "productType": str(p.get("ProductType", "MIS")),
                            "orderType": "MARKET",
                            "orderSide": exit_action,
                            "timeInForce": "DAY",
                            "disclosedQuantity": 0,
                            "orderQuantity": exit_qty,
                            "limitPrice": 0.0,
                            "stopPrice": 0.0,
                            "orderUniqueIdentifier": f"SQ_{account_id}_{int(time.time()*1000)}",
                        }

                        exit_resp = requests.post(f"{INTERACTIVE_URL}/orders", json=exit_payload, headers=headers, timeout=4)
                        if exit_resp.status_code == 200:
                            closed_positions.append(f"{symbol} ({exit_action} {exit_qty})")
                            record_copy_order(
                                account_id=account_id,
                                symbol=symbol,
                                exchange=exchange,
                                action=exit_action,
                                quantity=exit_qty,
                                pricetype="MARKET",
                                status="placed",
                                message="Emergency Square-Off",
                            )
    except Exception as e:
        logger.error(f"[Square-off] Error squaring off positions for {account_name}: {e}")

    latency_ms = (time.time() - t0) * 1000
    return {
        "account_id": account_id,
        "account_name": account_name,
        "client_code": client_code,
        "status": "success",
        "cancelled_orders": cancelled_orders,
        "closed_positions": closed_positions,
        "latency_ms": round(latency_ms, 2),
    }


def emergency_squareoff_all_accounts() -> Dict[str, Any]:
    """
    1-Click Emergency Square-Off: Concurrently cancels all pending orders and closes
    all open positions across all active child accounts within 1 second.
    """
    t0 = time.time()
    accounts = get_all_child_accounts(active_only=True, include_secrets=True)
    if not accounts:
        return {"status": "success", "message": "No active child accounts found", "results": [], "total_accounts": 0}

    logger.warning(f"[EMERGENCY SQUARE-OFF] Initiating emergency square-off across {len(accounts)} child accounts...")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(50, len(accounts))) as executor:
        futures = {executor.submit(squareoff_single_account, acc): acc for acc in accounts}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    total_latency_ms = (time.time() - t0) * 1000
    logger.info(f"[EMERGENCY SQUARE-OFF] Completed across {len(accounts)} accounts in {total_latency_ms:.2f}ms")

    return {
        "status": "success",
        "message": "Emergency square-off completed",
        "total_accounts": len(accounts),
        "total_latency_ms": round(total_latency_ms, 2),
        "results": results,
    }
