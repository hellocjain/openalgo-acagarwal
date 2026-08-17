"""
Risk Management & Emergency Square-Off Service for Copy Trading.
Adapted from Algomirror's position_monitor and risk_manager to provide 1-click Emergency
Square-Off All and real-time MTM Max Daily Loss circuit breakers across all AC Agarwal child accounts.
"""

import concurrent.futures
import os
import threading
import time
from datetime import datetime
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


def extract_xts_available_margin(f_data: Dict[str, Any]) -> float:
    """
    Extract available cash margin from any AC Agarwal Symphony XTS response format.
    Checks RMSSubLimits, RMSLimits, limitObject, and top-level response variations.
    """
    if not isinstance(f_data, dict):
        return 0.0

    result = f_data.get("result") or f_data
    if not isinstance(result, dict):
        return 0.0

    # 1. Check BalanceList array (standard XTS RMSSubLimits)
    bal_list = result.get("BalanceList") or []
    if isinstance(bal_list, list) and len(bal_list) > 0:
        for bal_item in bal_list:
            if not isinstance(bal_item, dict):
                continue
            limit_obj = bal_item.get("limitObject") or {}
            if isinstance(limit_obj, dict):
                rms_sub = limit_obj.get("RMSSubLimits") or {}
                if isinstance(rms_sub, dict):
                    for k in ["netMarginAvailable", "marginAvailable", "availableMargin", "cashBalance", "clearBalance", "collateral", "adhocMargin"]:
                        val = rms_sub.get(k)
                        if val is not None:
                            try:
                                f_val = float(val)
                                if f_val != 0.0:
                                    return f_val
                            except (ValueError, TypeError):
                                pass

                rms_lim = limit_obj.get("RMSLimits") or {}
                if isinstance(rms_lim, dict):
                    for k in ["netMarginAvailable", "marginAvailable", "availableMargin", "cashBalance", "clearBalance"]:
                        val = rms_lim.get(k)
                        if val is not None:
                            try:
                                f_val = float(val)
                                if f_val != 0.0:
                                    return f_val
                            except (ValueError, TypeError):
                                pass

                for k in ["netMarginAvailable", "marginAvailable", "availableMargin", "cashBalance", "collateralValue", "specialLimit"]:
                    val = limit_obj.get(k)
                    if val is not None:
                        try:
                            f_val = float(val)
                            if f_val != 0.0:
                                return f_val
                        except (ValueError, TypeError):
                            pass

    # 2. Check top-level result fields
    for k in ["availablecash", "availableBalance", "availableMargin", "netMarginAvailable", "cash", "cashBalance", "ledgerBalance"]:
        val = result.get(k)
        if val is not None:
            try:
                f_val = float(val)
                if f_val != 0.0:
                    return f_val
            except (ValueError, TypeError):
                pass

    return 0.0


def fetch_account_funds_and_pnl(account: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch live available funds and MTM PnL for a single child account from AC Agarwal."""
    account_id = account["id"]
    success, token, err = get_or_refresh_child_token(account)
    if not success or not token:
        return {"account_id": account_id, "status": "error", "message": err, "funds": 0.0, "pnl": 0.0}

    headers = {"Content-Type": "application/json", "Authorization": token, "authorization": token}
    funds_url = f"{INTERACTIVE_URL}/user/balance"
    positions_url = f"{INTERACTIVE_URL}/portfolio/positions?dayOrNet=NetWise"

    available_cash = 0.0
    total_pnl = 0.0
    positions_list = []

    # 1. Fetch balance
    try:
        f_resp = requests.get(funds_url, headers=headers, timeout=5)
        if f_resp.status_code == 200:
            f_data = f_resp.json()
            available_cash = extract_xts_available_margin(f_data)
            logger.info(f"[Risk] Fetched balance for {account['account_name']} ({account['client_code']}): Rs {available_cash:.2f}")
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

                        from services.copy_trading_service import slice_order_quantities
                        exit_slices = slice_order_quantities(exit_qty, symbol, exchange)

                        for chunk_qty in exit_slices:
                            exit_payload = {
                                "exchangeSegment": exchange,
                                "exchangeInstrumentID": token_id,
                                "productType": str(p.get("ProductType", "MIS")),
                                "orderType": "MARKET",
                                "orderSide": exit_action,
                                "timeInForce": "DAY",
                                "disclosedQuantity": 0,
                                "orderQuantity": chunk_qty,
                                "limitPrice": 0.0,
                                "stopPrice": 0.0,
                                "orderUniqueIdentifier": f"SQ_{account_id}_{int(time.time()*1000)}",
                            }

                            exit_resp = requests.post(f"{INTERACTIVE_URL}/orders", json=exit_payload, headers=headers, timeout=4)
                            if exit_resp.status_code == 200:
                                closed_positions.append(f"{symbol} ({exit_action} {chunk_qty})")
                                record_copy_order(
                                    account_id=account_id,
                                    symbol=symbol,
                                    exchange=exchange,
                                    action=exit_action,
                                    quantity=chunk_qty,
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


def squareoff_by_account_id(account_id: int) -> Dict[str, Any]:
    """Emergency square-off for a specific single client account."""
    from database.copy_trading_db import get_child_account
    account = get_child_account(account_id, include_secrets=True)
    if not account:
        return {"status": "error", "message": "Account not found"}
    return squareoff_single_account(account)


def cancel_orders_by_account_id(account_id: int) -> Dict[str, Any]:
    """Cancel all open pending orders for a specific client account."""
    from database.copy_trading_db import get_child_account
    account = get_child_account(account_id, include_secrets=True)
    if not account:
        return {"status": "error", "message": "Account not found"}

    success, token, err = get_or_refresh_child_token(account)
    if not success or not token:
        return {"status": "error", "message": f"Auth failed: {err}"}

    headers = {"Content-Type": "application/json", "Authorization": token}
    cancelled_orders = []

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
        return {"status": "success", "cancelled_orders": cancelled_orders, "message": f"Cancelled {len(cancelled_orders)} pending orders"}
    except Exception as e:
        logger.error(f"[Cancel Orders] Exception for {account.get('account_name')}: {e}")
        return {"status": "error", "message": str(e)}


def fetch_client_profile_details(account_id: int) -> Dict[str, Any]:
    """
    Fetch comprehensive live details for a single client to populate the Client Inspection Drawer:
    - Subscribed strategies with multipliers
    - Live net positions with LTP and PnL
    - Open pending orders
    - Recent executions
    """
    from database.copy_trading_db import (
        get_account_strategies,
        get_child_account,
        get_copy_orders,
    )
    account = get_child_account(account_id, include_secrets=True)
    if not account:
        return {"status": "error", "message": "Account not found"}

    strategies = get_account_strategies(account_id)
    recent_orders = get_copy_orders(limit=20, account_id=account_id)

    # Fetch live positions and orders from broker
    positions = []
    open_orders = []

    success, token, err = get_or_refresh_child_token(account)
    if success and token:
        headers = {"Authorization": token}
        try:
            p_resp = requests.get(f"{INTERACTIVE_URL}/portfolio/positions?dayOrNet=NetWise", headers=headers, timeout=4)
            if p_resp.status_code == 200:
                p_data = p_resp.json()
                if p_data.get("type") == "success":
                    raw_positions = p_data.get("result", {}).get("positionList", []) or []
                    for p in raw_positions:
                        qty = int(p.get("netQuantity", 0) or 0)
                        if qty != 0:
                            positions.append({
                                "symbol": p.get("TradingSymbol", ""),
                                "exchange": p.get("ExchangeSegment", "NSEFO"),
                                "quantity": qty,
                                "product": p.get("ProductType", "MIS"),
                                "avg_price": float(p.get("buyAveragePrice" if qty > 0 else "sellAveragePrice", 0.0) or 0.0),
                                "pnl": float(p.get("unrealizedMTM", 0.0) or 0.0) + float(p.get("realizedMTM", 0.0) or 0.0),
                            })
        except Exception as e:
            logger.debug(f"[Profile] Position fetch error for {account_id}: {e}")

        try:
            o_resp = requests.get(f"{INTERACTIVE_URL}/orders", headers=headers, timeout=4)
            if o_resp.status_code == 200:
                o_data = o_resp.json()
                if o_data.get("type") == "success":
                    raw_orders = o_data.get("result", []) or []
                    for o in raw_orders:
                        st = str(o.get("OrderStatus", "")).upper()
                        if st in ["OPEN", "PENDING", "NEW", "TRIGGER PENDING"]:
                            open_orders.append({
                                "order_id": str(o.get("AppOrderID", "")),
                                "symbol": o.get("TradingSymbol", ""),
                                "action": o.get("OrderSide", "BUY"),
                                "quantity": int(o.get("OrderQuantity", 0) or 0),
                                "price": float(o.get("OrderPrice", 0.0) or 0.0),
                                "status": st,
                            })
        except Exception as e:
            logger.debug(f"[Profile] Open orders fetch error for {account_id}: {e}")

    # Remove secret tokens before returning to UI
    account_safe = get_child_account(account_id, include_secrets=False)

    return {
        "status": "success",
        "account": account_safe,
        "strategies": strategies,
        "positions": positions,
        "open_orders": open_orders,
        "recent_orders": recent_orders,
    }


def run_premarket_fire_drill() -> Dict[str, Any]:
    """
    🎯 1-Click Pre-Market Fire Drill:
    Runs a zero-trade dry run across all 100+ child accounts at 9:00 AM, testing:
    - Session authentication & token freshness
    - Available cash margin vs minimum buffer (Rs 10,000)
    - Connection latency in milliseconds
    Returns a comprehensive pre-flight health report.
    """
    t0 = time.time()
    accounts = get_all_child_accounts(active_only=False, include_secrets=True)
    if not accounts:
        return {
            "status": "success",
            "message": "No child accounts configured",
            "total_tested": 0,
            "ready_count": 0,
            "issue_count": 0,
            "results": [],
        }

    logger.info(f"[Fire Drill] Starting pre-market dry run across {len(accounts)} accounts...")

    def _test_single(acc: Dict[str, Any]) -> Dict[str, Any]:
        acc_start = time.time()
        acc_id = acc["id"]
        success, token, err = get_or_refresh_child_token(acc)
        acc_latency = (time.time() - acc_start) * 1000

        if not success or not token:
            return {
                "account_id": acc_id,
                "account_name": acc["account_name"],
                "client_code": acc["client_code"],
                "status": "error",
                "ready": False,
                "issue": f"Login failed: {err}",
                "funds": 0.0,
                "latency_ms": round(acc_latency, 1),
            }

        # Check balance using comprehensive parser
        funds = 0.0
        try:
            b_resp = requests.get(f"{INTERACTIVE_URL}/user/balance", headers={"Authorization": token, "authorization": token}, timeout=5)
            if b_resp.status_code == 200:
                b_data = b_resp.json()
                funds = extract_xts_available_margin(b_data)
                update_account_status(acc_id, "connected", funds=funds)
        except Exception:
            pass

        is_low_margin = funds < 10000.0
        issue = "Low Margin (< Rs 10,000)" if is_low_margin else None

        return {
            "account_id": acc_id,
            "account_name": acc["account_name"],
            "client_code": acc["client_code"],
            "status": "warning" if is_low_margin else "success",
            "ready": not is_low_margin,
            "issue": issue,
            "funds": funds,
            "latency_ms": round(acc_latency, 1),
        }

    results = []
    ready_count = 0
    issue_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(30, len(accounts))) as executor:
        futures = {executor.submit(_test_single, acc): acc for acc in accounts}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)
            if res.get("ready"):
                ready_count += 1
            else:
                issue_count += 1

    total_time_ms = (time.time() - t0) * 1000
    logger.info(f"[Fire Drill] Completed in {total_time_ms:.1f}ms: {ready_count} Ready, {issue_count} Issues.")

    report = {
        "status": "success",
        "total_tested": len(accounts),
        "ready_count": ready_count,
        "issue_count": issue_count,
        "total_time_ms": round(total_time_ms, 1),
        "results": results,
    }

    # Automatically dispatch Telegram Morning Briefing
    dispatch_morning_telegram_report(report)

    return report


def dispatch_morning_telegram_report(report: Dict[str, Any]):
    """
    Asynchronously dispatch a comprehensive 8:30 AM pre-market readiness report to Telegram.
    """
    def _send():
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if not bot_token or not chat_id:
                return

            total = report.get("total_tested", 0)
            ready = report.get("ready_count", 0)
            issues = report.get("issue_count", 0)
            results = report.get("results", [])

            total_funds = sum(r.get("funds", 0.0) for r in results)
            avg_lat = sum(r.get("latency_ms", 0.0) for r in results) / max(1, len(results))

            status_icon = "🟢" if issues == 0 else ("🟡" if ready > 0 else "🔴")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            msg = (
                f"🌅 <b>OpenAlgo 08:30 AM Pre-Market Readiness Report</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 <b>Total Accounts:</b> {total}\n"
                f"🟢 <b>Ready & Logged In:</b> <b>{ready}</b>\n"
                f"🔴 <b>Need Attention:</b> <b>{issues}</b>\n"
                f"💰 <b>Total Margin Pool:</b> ₹{total_funds:,.2f}\n"
                f"⏱️ <b>Avg API Latency:</b> <code>{avg_lat:.1f}ms</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Highlight specific accounts needing attention
            problem_accs = [r for r in results if not r.get("ready")]
            if problem_accs:
                msg += "<b>⚠️ Accounts Requiring Action:</b>\n"
                for p in problem_accs[:8]:  # Limit top 8
                    msg += f"• <code>{p.get('client_code')}</code> ({p.get('account_name')}): {p.get('issue') or 'Auth Error'}\n"
                if len(problem_accs) > 8:
                    msg += f"<i>...and {len(problem_accs) - 8} more</i>\n"
                msg += "━━━━━━━━━━━━━━━━━━━━━\n"

            msg += f"⚡ <i>{ready} active accounts primed for 09:00 AM MCX & 09:15 AM NSE open!</i>"

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except Exception as ex:
            logger.debug(f"[Morning Telegram] Report dispatch notice: {ex}")

    threading.Thread(target=_send, daemon=True).start()


# =====================================================================
# 8:30 AM Automated Morning Scheduler Worker
# =====================================================================
_MORNING_SCHEDULER_RUNNING = False
_LAST_MORNING_RUN_DATE = None


def _morning_scheduler_worker():
    """
    Background daemon checking every 30 seconds for 08:30 AM (IST) on Monday-Friday.
    Automatically executes the pre-market login drill and sends the Telegram report.
    """
    global _MORNING_SCHEDULER_RUNNING, _LAST_MORNING_RUN_DATE
    logger.info("[Morning Bot] 08:30 AM Auto-Login & Health Monitor started.")

    while _MORNING_SCHEDULER_RUNNING:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # Check if weekday (Monday=0 to Friday=4)
            if now.weekday() < 5:
                # Target window: 08:30 AM to 08:35 AM
                if now.hour == 8 and now.minute >= 30:
                    if _LAST_MORNING_RUN_DATE != today_str:
                        logger.info(f"[Morning Bot] 08:30 AM triggered! Running automatic pre-market health check for {today_str}...")
                        _LAST_MORNING_RUN_DATE = today_str
                        run_premarket_fire_drill()
        except Exception as e:
            logger.error(f"[Morning Bot] Scheduler loop error: {e}")

        time.sleep(30)


def start_morning_autologin_scheduler():
    """Start the 08:30 AM morning auto-login scheduler thread."""
    global _MORNING_SCHEDULER_RUNNING
    if not _MORNING_SCHEDULER_RUNNING:
        _MORNING_SCHEDULER_RUNNING = True
        t = threading.Thread(target=_morning_scheduler_worker, daemon=True, name="MorningAutoLoginBot")
        t.start()
