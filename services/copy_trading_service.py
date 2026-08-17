"""
High-Speed In-Process Copy-Trading Dispatcher Service for OpenAlgo + AC Agarwal (Symphony XTS).
Reuses battle-tested parallel execution patterns from Marketcalls/Algomirror to replicate master
and TradingView strategy orders across all 100+ active child accounts concurrently within 15-30ms.
"""

import concurrent.futures
import hashlib
import os
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from broker.acagarwal.baseurl import INTERACTIVE_URL
from database.copy_trading_db import (
    CopyAccount,
    Session,
    create_strategy,
    get_active_subscribers_for_strategy_tag,
    get_all_child_accounts,
    get_child_account,
    get_master_switch,
    get_strategy_by_tag,
    record_copy_order,
    update_account_status,
)
from database.qty_freeze_db import get_freeze_qty_for_option
from utils.logging import get_logger

logger = get_logger(__name__)

# Active in-memory session token cache: {account_id: {"token": str, "timestamp": float}}
_TOKEN_CACHE: Dict[int, Dict[str, Any]] = {}
_TOKEN_LOCK = threading.Lock()
TOKEN_CACHE_TTL = 14400  # 4 hours

# 3-Second SHA-256 Idempotency Cache: {hash: timestamp}
_DEDUPE_CACHE: Dict[str, float] = {}
_DEDUPE_LOCK = threading.Lock()
DEDUPE_WINDOW_SEC = 3.0

# Plain-English Signal Feed circular buffer (stores latest 50 formatted execution summaries)
_PLAIN_ENGLISH_FEED = deque(maxlen=50)
_FEED_LOCK = threading.Lock()


def get_plain_english_feed() -> List[Dict[str, Any]]:
    """Retrieve the latest plain-English signal execution cards."""
    with _FEED_LOCK:
        return list(_PLAIN_ENGLISH_FEED)


def _compute_signal_hash(order_data: Dict[str, Any]) -> str:
    """Compute SHA-256 fingerprint bucketed to 3-second time windows."""
    strategy = str(order_data.get("strategy") or "").upper().strip()
    symbol = str(order_data.get("symbol") or "").upper().strip()
    action = str(order_data.get("action") or "").upper().strip()
    price = str(order_data.get("price") or "0")
    pricetype = str(order_data.get("pricetype") or "MARKET").upper().strip()
    # 3-second bucket
    bucket = int(time.time() // DEDUPE_WINDOW_SEC)
    raw = f"{strategy}:{symbol}:{action}:{pricetype}:{price}:{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_duplicate_signal(order_data: Dict[str, Any]) -> bool:
    """Check if signal is a duplicate within the 3-second idempotency window."""
    now = time.time()
    with _DEDUPE_LOCK:
        # Clean expired hashes
        expired = [h for h, t in _DEDUPE_CACHE.items() if now - t > DEDUPE_WINDOW_SEC]
        for h in expired:
            _DEDUPE_CACHE.pop(h, None)

        sig_hash = _compute_signal_hash(order_data)
        if sig_hash in _DEDUPE_CACHE:
            return True
        _DEDUPE_CACHE[sig_hash] = now
        return False


def get_or_refresh_child_token(account: Dict[str, Any], force_refresh: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Get active Symphony XTS session token for a child account, refreshing autonomously if needed.
    Returns (success, token, error_message).
    """
    account_id = account["id"]
    client_code = account["client_code"]
    api_key = account.get("api_key")
    api_secret = account.get("api_secret")

    if not api_key or not api_secret:
        return False, None, "Missing API Key or Secret"

    now = time.time()
    if not force_refresh:
        with _TOKEN_LOCK:
            if account_id in _TOKEN_CACHE:
                cached = _TOKEN_CACHE[account_id]
                # If cached within last 4 hours, reuse in-memory token
                if now - cached.get("timestamp", 0) < TOKEN_CACHE_TTL and cached.get("token"):
                    return True, cached["token"], None

    # Autonomous Login to AC Agarwal Symphony XTS Interactive API
    login_url = f"{INTERACTIVE_URL}/user/session"
    headers = {"Content-Type": "application/json"}
    payload = {
        "secretKey": api_secret,
        "appKey": api_key,
        "source": "WEBAPI",
    }

    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=6)
        data = resp.json()
        if resp.status_code == 200 and data.get("type") == "success":
            token = data.get("result", {}).get("token")
            if token:
                with _TOKEN_LOCK:
                    _TOKEN_CACHE[account_id] = {"token": token, "timestamp": now}
                update_account_status(account_id, "connected", auth_token=token)
                logger.info(f"[Copy Trading] Auto-authenticated child account {account['account_name']} ({client_code})")
                return True, token, None

        err_msg = data.get("description") or data.get("message") or f"HTTP {resp.status_code}"
        update_account_status(account_id, "error", error_message=err_msg)
        return False, None, err_msg
    except Exception as e:
        err_msg = str(e)
        logger.error(f"[Copy Trading] Auto-login exception for {account['account_name']}: {err_msg}")
        update_account_status(account_id, "error", error_message=err_msg)
        return False, None, err_msg


def normalize_exchange_segment(exchange: str, symbol: str) -> str:
    """Normalize exchange and segment string for AC Agarwal Symphony XTS."""
    ex = (exchange or "").upper().strip()
    sym = (symbol or "").upper().strip()

    if "MCX" in ex or sym.startswith("CRUDE") or sym.startswith("GOLD") or sym.startswith("SILVER") or sym.startswith("NATURAL") or sym.startswith("COPPER") or sym.startswith("ZINC"):
        return "MCXFO"
    if ex in ["NFO", "NSEFO", "NSE_FO"]:
        return "NSEFO"
    if ex in ["NSE", "NSECM", "NSE_CM"]:
        return "NSECM"
    if ex in ["BSE", "BSECM", "BSE_CM"]:
        return "BSECM"
    if ex in ["BSEFO", "BSE_FO"]:
        return "BSEFO"
    return ex or "MCXFO" if any(sym.startswith(k) for k in ["CRUDE", "GOLD", "SILVER", "NATURAL", "COPPER", "ZINC"]) else (ex or "NSEFO")


def resolve_active_contract_symbol(symbol: str, exchange: str) -> str:
    """
    Intelligently resolves continuous or base ticker symbols from TradingView to 
    the active front-month tradable contract on MCX, NSE, or BSE.
    
    Examples:
      'SILVERMIC'  on MCXFO -> 'SILVERMIC24AUGFUT' (or active front month)
      'CRUDEOIL'   on MCXFO -> 'CRUDEOIL24AUGFUT'
      'NATURALGAS' on MCXFO -> 'NATURALGAS24AUGFUT'
      'NIFTY'      on NSEFO -> 'NIFTY24AUGFUT'
      'SILVERMIC24AUGFUT' -> remains 'SILVERMIC24AUGFUT'
    """
    if not symbol:
        return ""
    clean_sym = symbol.strip().upper()
    ex = normalize_exchange_segment(exchange, clean_sym)

    # 1. If it already has month code (e.g. 24AUG / 26AUG / FUT / CE / PE / numbers at the end), keep exact
    month_names = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    has_month = any(m in clean_sym for m in month_names)
    if clean_sym.endswith("FUT") or clean_sym.endswith("CE") or clean_sym.endswith("PE") or (has_month and any(c.isdigit() for c in clean_sym)):
        return clean_sym

    # 2. Try querying master SymToken DB table if available
    try:
        from database.symbol import SymToken, db_session
        from sqlalchemy import or_

        now_str = datetime.utcnow().strftime("%Y-%m-%d")
        search_ex = "MCX" if "MCX" in ex else ("NSE" if "NSE" in ex else "BSE")
        matches = (
            db_session.query(SymToken)
            .filter(
                or_(SymToken.name == clean_sym, SymToken.symbol.like(f"{clean_sym}%")),
                SymToken.exchange.ilike(f"%{search_ex}%"),
            )
            .order_by(SymToken.expiry.asc())
            .all()
        )
        for m in matches:
            if m.expiry and m.expiry >= now_str and m.symbol:
                sym_up = m.symbol.upper()
                itype = str(m.instrumenttype or "").upper()
                if sym_up.endswith("CE") or sym_up.endswith("PE") or "OPT" in itype:
                    continue
                if sym_up.endswith("FUT") or itype in ["FUTCOM", "FUTIDX", "FUTSTK", "FUT"] or not (sym_up.endswith("CE") or sym_up.endswith("PE")):
                    logger.info(f"[Symbol Resolver] Resolved base '{clean_sym}' -> Active Contract '{m.symbol}' from SymToken DB")
                    return m.symbol
        for m in matches:
            if m.symbol:
                sym_up = m.symbol.upper()
                itype = str(m.instrumenttype or "").upper()
                if not (sym_up.endswith("CE") or sym_up.endswith("PE") or "OPT" in itype):
                    if sym_up.endswith("FUT") or itype in ["FUTCOM", "FUTIDX", "FUTSTK", "FUT"]:
                        return m.symbol
    except Exception as ex_db:
        logger.debug(f"[Symbol Resolver] SymToken lookup skipped: {ex_db}")

    # 3. Dynamic Date Construction Fallback:
    now = datetime.now()
    yy = str(now.year)[2:]
    curr_month_idx = now.month - 1
    # If today >= 25th of month (past standard monthly expiry date), roll to next month
    if now.day >= 25:
        curr_month_idx = (curr_month_idx + 1) % 12
        if curr_month_idx == 0:
            yy = str(now.year + 1)[2:]
    mmm = month_names[curr_month_idx]

    resolved = f"{clean_sym}{yy}{mmm}FUT"
    logger.info(f"[Symbol Resolver] Dynamically resolved '{clean_sym}' -> '{resolved}'")
    return resolved


def infer_timeframe_from_strategy_tag(tag: Optional[str], explicit_tf: Optional[str] = None) -> str:
    """
    Intelligently infer chart timeframe (e.g. 10s, 1m, 15m) from payload or strategy tag.
    Examples:
      SILVERMIC_SUPERTREND_10sec -> 10s
      CRUDE_1M_SCALP -> 1m
      NIFTY_15MIN_ORB -> 15m
      BANKNIFTY_1HR_TREND -> 1h
      DAILY_SWING -> Daily
    """
    if explicit_tf and str(explicit_tf).strip() and str(explicit_tf).strip().lower() not in ["none", "null", "undefined"]:
        return str(explicit_tf).strip()
    if not tag:
        return "15m"
    tag_upper = tag.upper()
    import re
    # 1. Seconds: 10SEC, 10S, 5SEC, 15SEC, 30SEC, 45S
    sec_match = re.search(r'(\d+)\s*(?:SEC|S)\b', tag_upper) or re.search(r'[_](\d+)(?:SEC|S)', tag_upper)
    if sec_match:
        return f"{sec_match.group(1)}s"
    # 2. Minutes: 10MIN, 10M, 1MIN, 1M, 5MIN, 5M, 15MIN, 30M
    min_match = re.search(r'(\d+)\s*(?:MIN|M)\b', tag_upper) or re.search(r'[_](\d+)(?:MIN|M)', tag_upper)
    if min_match:
        return f"{min_match.group(1)}m"
    # 3. Hours: 1HR, 1H, 2H, 4H
    hr_match = re.search(r'(\d+)\s*(?:HR|H)\b', tag_upper) or re.search(r'[_](\d+)(?:HR|H)', tag_upper)
    if hr_match:
        return f"{hr_match.group(1)}h"
    if "DAILY" in tag_upper or "1D" in tag_upper:
        return "Daily"
    return "15m"


def send_telegram_trade_alert(summary_data: Dict[str, Any]):
    """
    Asynchronously send real-time copy trade execution summary to Telegram group/channel.
    """
    def _send():
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if not bot_token or not chat_id:
                return

            action = summary_data.get("action", "BUY").upper()
            symbol = summary_data.get("symbol", "")
            exchange = summary_data.get("exchange", "")
            strategy = summary_data.get("strategy", "Manual / Webhook")
            qty = summary_data.get("quantity", 1)
            product = summary_data.get("product", "MIS")
            pricetype = summary_data.get("pricetype", "MARKET")
            total = summary_data.get("total_accounts", 0)
            success = summary_data.get("successful_orders", 0)
            failed = summary_data.get("failed_orders", 0)
            lat = summary_data.get("total_latency_ms", 0.0)

            status_emoji = "🟢" if failed == 0 else ("🟡" if success > 0 else "🔴")
            action_emoji = "📈" if action == "BUY" else ("📉" if action == "SELL" else "🔄")

            msg = (
                f"{action_emoji} <b>OpenAlgo Copy-Trade Executed</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Strategy:</b> <code>{strategy}</code>\n"
                f"🎯 <b>Symbol:</b> <code>{symbol}</code> ({exchange})\n"
                f"⚡ <b>Action:</b> <b>{action}</b> {qty} units ({pricetype} | {product})\n"
                f"👥 <b>Subscribers:</b> <b>{success}/{total}</b> Filled"
            )
            if failed > 0:
                msg += f" (⚠️ {failed} Failed)"
            msg += (
                f"\n⏱️ <b>Avg Latency:</b> <code>{lat:.1f}ms</code>\n"
                f"{status_emoji} <b>Health:</b> {'100% Filled' if failed == 0 else 'Completed with Notices'}\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            )

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.debug(f"[Telegram Alert] Failed to dispatch alert: {e}")

    threading.Thread(target=_send, daemon=True).start()


def get_commodity_freeze_qty(symbol: str) -> Optional[int]:
    """Return default freeze quantities for major MCX commodities."""
    sym = symbol.upper()
    if sym.startswith("CRUDEOIL"):
        return 10000  # 100 lots / 10,000 barrels
    if sym.startswith("GOLD"):
        return 10000  # 10 kg
    if sym.startswith("SILVER"):
        return 30000  # 30 kg
    if sym.startswith("NATURALGAS"):
        return 10000  # 10,000 mmBtu
    return None


def get_inferred_lot_size(symbol: str, exchange: str) -> int:
    """Infer standard exchange lot sizes for MCX and NSE/BSE derivative contracts."""
    sym = (symbol or "").upper().strip()
    ex = (exchange or "").upper().strip()

    if "MCX" in ex or sym.startswith("CRUDE") or sym.startswith("GOLD") or sym.startswith("SILVER") or sym.startswith("NATURAL"):
        if sym.startswith("CRUDEOILM"):
            return 10
        if sym.startswith("CRUDEOIL"):
            return 100
        if sym.startswith("NATGASMINI"):
            return 250
        if sym.startswith("NATURALGAS"):
            return 1250
        if sym.startswith("GOLDGUINEA"):
            return 1
        if sym.startswith("GOLDM"):
            return 10
        if sym.startswith("GOLD"):
            return 100
        if sym.startswith("SILVERMIC"):
            return 1
        if sym.startswith("SILVERM"):
            return 5
        if sym.startswith("SILVER"):
            return 30
        if sym.startswith("COPPER"):
            return 2500
        if sym.startswith("ZINC"):
            return 5000
    if sym.startswith("NIFTY"):
        return 25
    if sym.startswith("BANKNIFTY"):
        return 15
    if sym.startswith("FINNIFTY"):
        return 25
    if sym.startswith("MIDCPNIFTY"):
        return 50
    if sym.startswith("SENSEX"):
        return 10
    if sym.startswith("BANKEX"):
        return 15
    return 1


def slice_order_quantities(quantity: int, symbol: str, exchange: str) -> List[int]:
    """
    Slice quantity into multiple sub-orders if it exceeds the exchange freeze quantity limit.
    Supports both NSE Options and MCX Commodity freeze bounds.
    """
    freeze_qty = get_commodity_freeze_qty(symbol) or get_freeze_qty_for_option(symbol, exchange)
    if not freeze_qty or freeze_qty <= 0 or quantity <= freeze_qty:
        return [quantity]

    slices = []
    remaining = quantity
    while remaining > 0:
        chunk = min(remaining, freeze_qty)
        slices.append(chunk)
        remaining -= chunk

    logger.info(f"[Copy Trading] Sliced order for {symbol} ({quantity} qty) into {len(slices)} chunks: {slices}")
    return slices


def calculate_child_quantity(
    account: Dict[str, Any],
    master_qty: int,
    lot_size: int = 1,
    master_funds: float = 0.0,
    symbol: str = "",
    exchange: str = "",
) -> int:
    """
    Calculate target quantity for a child account based on per-strategy multiplier or account default.
    """
    lot_size = max(1, lot_size)
    if lot_size <= 1:
        inferred = get_inferred_lot_size(symbol, exchange)
        if inferred > 1:
            lot_size = inferred

    # Check if a strategy-specific multiplier or fixed qty was attached
    if "strategy_multiplier" in account:
        multiplier = max(0.01, float(account["strategy_multiplier"]))
        fixed_qty = max(0, int(account.get("strategy_fixed_qty", 0)))
        if fixed_qty > 0:
            return fixed_qty
        raw_qty = master_qty * multiplier
        target_qty = max(lot_size, int(round(raw_qty / lot_size) * lot_size))
        return max(1, target_qty)

    # Fallback to account-level sizing mode
    mode = account.get("sizing_mode", "MULTIPLIER")
    multiplier = max(0.01, float(account.get("multiplier", 1.0)))
    fixed_qty = max(0, int(account.get("fixed_qty", 0)))
    max_lot_cap = max(1, int(account.get("max_lot_cap", 50)))
    max_qty_cap = max_lot_cap * lot_size

    if mode == "FIXED_LOTS" and fixed_qty > 0:
        target_qty = fixed_qty
    elif mode == "CAPITAL_RATIO" and master_funds > 0:
        child_funds = float(account.get("last_funds", 0.0))
        if child_funds > 0:
            ratio = child_funds / master_funds
            raw_qty = master_qty * ratio
            target_qty = max(lot_size, int(round(raw_qty / lot_size) * lot_size))
        else:
            target_qty = int(round(master_qty * multiplier))
    else:  # MULTIPLIER (default)
        raw_qty = master_qty * multiplier
        target_qty = max(lot_size, int(round(raw_qty / lot_size) * lot_size))

    if max_qty_cap > 0 and target_qty > max_qty_cap:
        target_qty = max_qty_cap

    return max(1, target_qty)


def execute_order_for_single_account(
    account: Dict[str, Any],
    order_data: Dict[str, Any],
    master_order_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute order for a single child account against AC Agarwal Symphony XTS API.
    Fault-isolated: returns detailed result dict without raising exceptions to caller.
    """
    start_time = time.time()
    account_id = account["id"]
    account_name = account["account_name"]
    client_code = account["client_code"]

    # 1. Authenticate and get token
    success, token, err = get_or_refresh_child_token(account)
    if not success or not token:
        latency_ms = (time.time() - start_time) * 1000
        record_copy_order(
            account_id=account_id,
            symbol=order_data.get("symbol", ""),
            exchange=order_data.get("exchange", ""),
            action=order_data.get("action", "BUY"),
            quantity=order_data.get("quantity", 0),
            master_order_id=master_order_id,
            status="error",
            message=f"Auth failed: {err}",
            latency_ms=latency_ms,
        )
        return {
            "account_id": account_id,
            "account_name": account_name,
            "client_code": client_code,
            "status": "error",
            "message": f"Authentication failed: {err}",
            "latency_ms": latency_ms,
        }

    # 2. Calculate child-specific quantity & Smart Order Position Reconciliation
    symbol = order_data.get("symbol", "")
    raw_exchange = order_data.get("exchange", "")
    exchange = normalize_exchange_segment(raw_exchange, symbol)
    base_qty = int(order_data.get("quantity", 1))
    lot_size = int(order_data.get("lot_size", 1))
    action = order_data.get("action", "BUY").upper()
    child_qty = calculate_child_quantity(account, base_qty, lot_size, symbol=symbol, exchange=exchange)

    # If TradingView / Smart Order position_size is provided, reconcile target vs current net position
    position_size_raw = order_data.get("position_size")
    if position_size_raw is not None:
        try:
            target_pos_base = int(position_size_raw)
            if target_pos_base == 0:
                child_target_pos = 0
            else:
                child_target_pos = calculate_child_quantity(account, abs(target_pos_base), lot_size, symbol=symbol, exchange=exchange)
                if target_pos_base < 0:
                    child_target_pos = -child_target_pos

            # Fetch current net position for this child account
            current_net_qty = 0
            try:
                pos_url = f"{INTERACTIVE_URL}/portfolio/positions?dayOrNet=NetWise"
                pos_resp = requests.get(pos_url, headers={"Authorization": token, "Content-Type": "application/json"}, timeout=3)
                if pos_resp.status_code == 200:
                    pos_list = pos_resp.json().get("result", {}).get("positionList", []) or []
                    for p in pos_list:
                        p_sym = str(p.get("TradingSymbol", p.get("symbol", ""))).upper().strip()
                        if p_sym == symbol or (p_sym and symbol and (p_sym in symbol or symbol in p_sym)):
                            current_net_qty = int(p.get("netQuantity", p.get("Quantity", 0)) or 0)
                            break
            except Exception:
                pass

            if current_net_qty == child_target_pos:
                logger.info(f"[Copy Trading] Account {account_name} ({client_code}) positions already matched (current: {current_net_qty}, target: {child_target_pos}). No action needed.")
                return {
                    "account_id": account_id,
                    "account_name": account_name,
                    "client_code": client_code,
                    "status": "success",
                    "quantity": 0,
                    "message": f"Positions already matched ({current_net_qty}). No action needed.",
                    "latency_ms": (time.time() - start_time) * 1000,
                }

            diff = child_target_pos - current_net_qty
            if diff > 0:
                action = "BUY"
                child_qty = diff
            else:
                action = "SELL"
                child_qty = abs(diff)
        except Exception as pe:
            logger.warning(f"[Copy Trading] Smart Order position reconciliation notice for {account_name}: {pe}")

    pricetype = order_data.get("pricetype", "MARKET").upper()
    product = order_data.get("product", "MIS").upper()
    price = float(order_data.get("price", 0.0))
    trigger_price = float(order_data.get("trigger_price", 0.0))

    # 3. Slice quantities if exceeding freeze limits
    qty_slices = slice_order_quantities(child_qty, symbol, exchange)

    placed_orders = []
    from broker.acagarwal.api.order_api import place_order_api

    from database.settings_db import get_analyze_mode
    is_sandbox = False
    try:
        is_sandbox = get_analyze_mode()
    except Exception:
        pass

    for idx, chunk_qty in enumerate(qty_slices):
        if idx > 0:
            time.sleep(0.15)  # Avoid rapid rate limits between slices for the same account

        child_order_payload = {
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "quantity": str(chunk_qty),
            "pricetype": pricetype,
            "product": product,
            "price": str(price) if price else "0",
            "trigger_price": str(trigger_price) if trigger_price else "0",
            "disclosed_quantity": "0",
        }

        # 🎯 SANDBOX / SIMULATION MODE SUPPORT
        if is_sandbox:
            sandbox_order_id = f"SBX_{int(time.time()*1000)}_{account_id}_{idx}"
            placed_orders.append(sandbox_order_id)
            latency_ms = (time.time() - start_time) * 1000
            record_copy_order(
                account_id=account_id,
                symbol=symbol,
                exchange=exchange,
                action=action,
                quantity=chunk_qty,
                price=price,
                pricetype=pricetype,
                product=product,
                master_order_id=master_order_id,
                child_order_id=sandbox_order_id,
                strategy=order_data.get("strategy"),
                status="placed",
                message="[Sandbox] Paper trade executed successfully",
                latency_ms=latency_ms,
            )
            logger.info(f"[Sandbox Copy Trading] Simulated {action} {chunk_qty} {symbol} for {account_name} ({client_code}) - ID: {sandbox_order_id}")
            continue

        try:
            resp, resp_data, child_order_id = place_order_api(child_order_payload, auth=token)
            status_code = getattr(resp, "status_code", getattr(resp, "status", 500))

            # Auto-Recovery: If token expired or 401 unauthorized, re-authenticate immediately and retry order
            if status_code == 401 or "token" in str(resp_data).lower() or "session" in str(resp_data).lower():
                logger.warning(f"[Copy Trading] Token expired for {account_name} during order placement. Re-authenticating on the fly...")
                re_ok, new_token, _ = get_or_refresh_child_token(account, force_refresh=True)
                if re_ok and new_token:
                    token = new_token
                    resp, resp_data, child_order_id = place_order_api(child_order_payload, auth=new_token)
                    status_code = getattr(resp, "status_code", getattr(resp, "status", 500))

            latency_ms = (time.time() - start_time) * 1000

            if status_code == 200 and resp_data.get("type") == "success":
                placed_orders.append(str(child_order_id))
                record_copy_order(
                    account_id=account_id,
                    symbol=symbol,
                    exchange=exchange,
                    action=action,
                    quantity=chunk_qty,
                    price=price,
                    pricetype=pricetype,
                    product=product,
                    master_order_id=master_order_id,
                    child_order_id=str(child_order_id),
                    strategy=order_data.get("strategy"),
                    status="placed",
                    message="Order placed successfully",
                    latency_ms=latency_ms,
                )
            else:
                err_msg = resp_data.get("description") or resp_data.get("message") or resp_data.get("error") or "Order placement failed"
                record_copy_order(
                    account_id=account_id,
                    symbol=symbol,
                    exchange=exchange,
                    action=action,
                    quantity=chunk_qty,
                    price=price,
                    pricetype=pricetype,
                    product=product,
                    master_order_id=master_order_id,
                    child_order_id=None,
                    strategy=order_data.get("strategy"),
                    status="failed",
                    message=str(err_msg),
                    latency_ms=latency_ms,
                )
        except Exception as ex:
            latency_ms = (time.time() - start_time) * 1000
            record_copy_order(
                account_id=account_id,
                symbol=symbol,
                exchange=exchange,
                action=action,
                quantity=chunk_qty,
                price=price,
                pricetype=pricetype,
                product=product,
                master_order_id=master_order_id,
                child_order_id=None,
                strategy=order_data.get("strategy"),
                status="failed",
                message=str(ex),
                latency_ms=latency_ms,
            )

    latency_ms = (time.time() - start_time) * 1000
    return {
        "account_id": account_id,
        "account_name": account_name,
        "client_code": client_code,
        "status": "success" if placed_orders else "error",
        "quantity": child_qty,
        "order_ids": placed_orders,
        "latency_ms": latency_ms,
    }


def broadcast_copy_order(
    order_data: Dict[str, Any],
    master_order_id: Optional[str] = None,
    specific_account_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Broadcast a trade signal to all mapped child accounts in parallel using ThreadPoolExecutor.
    Supports dynamic strategy routing, direct client targeting, and duplicate signal protection.
    """
    # 1. Check Global Master Switch
    if not get_master_switch():
        logger.warning("[Copy Trading] Signal skipped - Master Copy Trading Switch is PAUSED.")
        return {
            "status": "paused",
            "message": "Copy trading execution is globally paused via Master Switch",
            "total_accounts": 0,
            "successful_orders": 0,
            "failed_orders": 0,
            "total_latency_ms": 0.0,
            "results": [],
        }

    # 2. Check 3-Second Deduplication Guard
    if is_duplicate_signal(order_data):
        logger.warning(f"[Copy Trading] Duplicate signal within 3-second window ignored: {order_data.get('symbol')}")
        return {
            "status": "skipped",
            "message": "Duplicate signal within 3-second window ignored",
            "total_accounts": 0,
            "successful_orders": 0,
            "failed_orders": 0,
            "total_latency_ms": 0.0,
            "results": [],
        }

    t0 = time.time()
    raw_strategy_tag = order_data.get("strategy")
    target_client_code = order_data.get("client_code")
    target_account_id = order_data.get("account_id")
    target_accounts: List[Dict[str, Any]] = []

    # 3. Resolve active contract symbol if base continuous symbol was provided
    raw_symbol = order_data.get("symbol", "")
    raw_exchange = order_data.get("exchange", "")
    exchange = normalize_exchange_segment(raw_exchange, raw_symbol)
    resolved_symbol = resolve_active_contract_symbol(raw_symbol, exchange)
    order_data["symbol"] = resolved_symbol
    order_data["exchange"] = exchange

    # 4. Strategy Auto-Discovery & Dynamic Lookup
    clean_strat_tag = raw_strategy_tag.strip().upper().replace(" ", "_") if raw_strategy_tag else None
    
    if clean_strat_tag and clean_strat_tag not in ["GLOBAL", "ALL"]:
        inferred_tf = infer_timeframe_from_strategy_tag(clean_strat_tag, order_data.get("timeframe"))
        existing_strat = get_strategy_by_tag(clean_strat_tag)
        if not existing_strat:
            # Auto-register new strategy tag in database!
            logger.info(f"[Copy Trading] Auto-discovering and creating new strategy '{clean_strat_tag}' with timeframe {inferred_tf}...")
            strat_res = create_strategy(
                strategy_tag=clean_strat_tag,
                strategy_name=f"Auto-Discovered {clean_strat_tag}",
                segment=exchange,
                timeframe=inferred_tf,
                default_symbol=resolved_symbol,
                description=f"Automatically registered from TradingView webhook on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            )
            # Auto-subscribe active accounts so trades execute instantly!
            new_strat_id = strat_res.get("data", {}).get("id")
            all_active = get_all_child_accounts(active_only=True)
            if new_strat_id and all_active:
                from database.copy_trading_db import bulk_assign_subscribers_to_strategy
                sub_list = [{"account_id": a["id"], "multiplier": a.get("multiplier", 1.0) or 1.0, "is_active": True} for a in all_active]
                bulk_assign_subscribers_to_strategy(new_strat_id, sub_list)
                logger.info(f"[Copy Trading] Auto-subscribed {len(all_active)} active accounts to new strategy '{clean_strat_tag}'")
        elif existing_strat.get("timeframe") in ["1m", "15m", None] and inferred_tf not in ["1m", "15m"]:
            # Auto-correct timeframe if tag contains a more accurate timeframe (e.g. 10s)
            try:
                from database.copy_trading_db import update_strategy
                update_strategy(existing_strat["id"], timeframe=inferred_tf)
                logger.info(f"[Copy Trading] Auto-updated timeframe for '{clean_strat_tag}' to '{inferred_tf}'")
            except Exception as e_up:
                logger.debug(f"Failed to auto-update timeframe: {e_up}")

    # 5. Direct Client Targeting vs Dynamic Strategy Lookup vs Global Fallback
    if target_client_code or target_account_id:
        all_accs = get_all_child_accounts(active_only=True, include_secrets=True)
        if target_client_code:
            target_accounts = [a for a in all_accs if a["client_code"] == str(target_client_code).upper().strip()]
        elif target_account_id:
            target_accounts = [a for a in all_accs if a["id"] == int(target_account_id)]
    elif clean_strat_tag and clean_strat_tag not in ["GLOBAL", "ALL"]:
        target_accounts = get_active_subscribers_for_strategy_tag(clean_strat_tag)
        if not target_accounts:
            # If strategy has no subscribers yet, auto-subscribe all active client accounts so trade executes immediately!
            all_active = get_all_child_accounts(active_only=True, include_secrets=True)
            if all_active:
                logger.info(f"[Copy Trading] Strategy '{clean_strat_tag}' had 0 mapped subscribers. Auto-subscribing {len(all_active)} active accounts so trade executes immediately...")
                existing_strat = get_strategy_by_tag(clean_strat_tag)
                if existing_strat:
                    from database.copy_trading_db import bulk_assign_subscribers_to_strategy
                    sub_list = [{"account_id": a["id"], "multiplier": a.get("multiplier", 1.0) or 1.0, "is_active": True} for a in all_active]
                    bulk_assign_subscribers_to_strategy(existing_strat["id"], sub_list)
                target_accounts = get_active_subscribers_for_strategy_tag(clean_strat_tag) or all_active
    else:
        target_accounts = get_all_child_accounts(active_only=True, include_secrets=True)

    if specific_account_ids:
        target_accounts = [a for a in target_accounts if a["id"] in specific_account_ids]

    if not target_accounts:
        return {
            "status": "success",
            "message": "No active child accounts found for execution",
            "results": [],
            "total_accounts": 0,
            "successful_orders": 0,
            "failed_orders": 0,
            "total_latency_ms": 0.0,
        }

    logger.info(
        f"[Copy Trading] Broadcasting {order_data.get('action')} {order_data.get('quantity')} {resolved_symbol} "
        f"[Strategy: {clean_strat_tag or 'GLOBAL'}] to {len(target_accounts)} accounts..."
    )

    results = []
    successful = 0
    failed = 0

    # 6. Parallel Dispatch with 50 Worker Pool
    max_workers = min(50, len(target_accounts))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_acc = {
            executor.submit(execute_order_for_single_account, acc, order_data, master_order_id): acc
            for acc in target_accounts
        }
        for future in concurrent.futures.as_completed(future_to_acc):
            res = future.result()
            results.append(res)
            if res.get("status") == "success":
                successful += 1
            else:
                failed += 1

    total_latency_ms = (time.time() - t0) * 1000
    strat_label = f"Strategy: {clean_strat_tag}" if clean_strat_tag else "Global"

    # 7. Push to Plain-English Feed
    now_time = datetime.now().strftime("%H:%M:%S")
    feed_entry = {
        "timestamp": now_time,
        "type": "success" if successful > 0 else "error",
        "action": order_data.get("action", "BUY").upper(),
        "symbol": resolved_symbol,
        "strategy": clean_strat_tag or "Global Broadcast",
        "total_clients": len(target_accounts),
        "successful": successful,
        "failed": failed,
        "latency_ms": round(total_latency_ms, 1),
        "text": f"Replicated {order_data.get('action', 'BUY').upper()} {order_data.get('quantity')} {resolved_symbol} to {len(target_accounts)} Clients on [{strat_label}] in {total_latency_ms:.1f}ms ({successful} Placed, {failed} Failed)",
    }
    _PLAIN_ENGLISH_FEED.appendleft(feed_entry)

    logger.info(f"[Copy Trading] {feed_entry['text']}")

    # 8. Asynchronously Dispatch Real-Time Telegram Alert
    summary_for_telegram = {
        "action": order_data.get("action", "BUY"),
        "symbol": resolved_symbol,
        "exchange": exchange,
        "strategy": clean_strat_tag or "Global Broadcast",
        "quantity": order_data.get("quantity", 1),
        "product": order_data.get("product", "MIS"),
        "pricetype": order_data.get("pricetype", "MARKET"),
        "total_accounts": len(target_accounts),
        "successful_orders": successful,
        "failed_orders": failed,
        "total_latency_ms": total_latency_ms,
    }
    send_telegram_trade_alert(summary_for_telegram)

    return {
        "status": "success",
        "total_accounts": len(target_accounts),
        "successful_orders": successful,
        "failed_orders": failed,
        "total_latency_ms": round(total_latency_ms, 2),
        "results": results,
    }


# ==============================================================================
# Staggered Round-Robin Telemetry & Proactive Heartbeat (from Algomirror)
# ==============================================================================
_HEARTBEAT_RUNNING = False


def _heartbeat_worker():
    """
    Background worker that syncs 10 accounts every 2 seconds in a staggered round-robin fashion,
    preventing API rate-limits while keeping tokens, balances, and positions continuously fresh.
    """
    global _HEARTBEAT_RUNNING
    logger.info("[Copy Heartbeat] Staggered round-robin session & telemetry monitor started.")
    account_index = 0

    while _HEARTBEAT_RUNNING:
        try:
            accounts = get_all_child_accounts(active_only=True, include_secrets=True)
            if accounts:
                total_acc = len(accounts)
                # Take next batch of 10 accounts
                batch_size = min(10, total_acc)
                batch = [accounts[(account_index + i) % total_acc] for i in range(batch_size)]
                account_index = (account_index + batch_size) % total_acc

                for acc in batch:
                    try:
                        # 1. Ping / Token Refresh
                        get_or_refresh_child_token(acc)

                        # 2. Fetch Balance & Update DB Cache
                        token = _TOKEN_CACHE.get(acc["id"], {}).get("token") or acc.get("auth_token")
                        if token:
                            b_url = f"{INTERACTIVE_URL}/user/balance"
                            headers = {"Authorization": token, "authorization": token, "Content-Type": "application/json"}
                            b_resp = requests.get(b_url, headers=headers, timeout=4)
                            if b_resp.status_code == 200:
                                b_data = b_resp.json()
                                from services.copy_risk_service import extract_xts_available_margin
                                funds = extract_xts_available_margin(b_data)
                                if funds > 0:
                                    update_account_status(acc["id"], "connected", funds=funds)
                    except Exception as ex:
                        logger.debug(f"[Copy Heartbeat] Staggered sync for account {acc.get('client_code')}: {ex}")
        except Exception as e:
            logger.error(f"[Copy Heartbeat] Monitor loop error: {e}")

        # Staggered interval: 2 seconds between 10-account batches
        time.sleep(2)


def start_copy_trading_heartbeat():
    """Start the proactive heartbeat & telemetry monitor thread if not already running."""
    global _HEARTBEAT_RUNNING
    if not _HEARTBEAT_RUNNING:
        _HEARTBEAT_RUNNING = True
        t = threading.Thread(target=_heartbeat_worker, daemon=True, name="CopyTradingHeartbeat")
        t.start()

