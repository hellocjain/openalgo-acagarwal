# broker/acagarwal/api/order_api.py

import json
import os
import threading
import time

import httpx
from broker.acagarwal.api.data import BrokerData
from broker.acagarwal.baseurl import INTERACTIVE_URL
from broker.acagarwal.mapping.transform_data import (
    map_product_type,
    reverse_map_product_type,
    transform_data,
    transform_modify_order_data,
)
from database.qty_freeze_db import get_freeze_qty_for_option
from database.token_db import get_br_symbol, get_symbol_info, get_token
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def get_api_response(endpoint, auth, method="GET", payload=""):
    AUTH_TOKEN = auth
    client = get_httpx_client()
    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    url = f"{INTERACTIVE_URL}{endpoint}"

    if method == "GET":
        response = client.get(url, headers=headers)
    elif method == "POST":
        response = client.post(url, headers=headers, json=payload)
    else:
        response = client.request(method, url, headers=headers, json=payload)

    response.status = response.status_code
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text}


def get_order_book(auth):
    return get_api_response("/orders", auth)


def get_trade_book(auth):
    return get_api_response("/orders/trades", auth)


def get_positions(auth):
    return get_api_response("/portfolio/positions?dayOrNet=NetWise", auth)


def get_holdings(auth):
    return get_api_response("/portfolio/holdings", auth)


# --- Per-Symbol Smart Order Lock ---
_symbol_locks = {}
_symbol_locks_lock = threading.Lock()

# --- Position Book Cache ---
_position_cache = {}
_position_cache_lock = threading.Lock()
_POSITION_CACHE_TTL = 1.0


def _get_symbol_lock(symbol, exchange, product):
    key = f"{symbol}:{exchange}:{product}"
    with _symbol_locks_lock:
        if key not in _symbol_locks:
            _symbol_locks[key] = threading.Lock()
        return _symbol_locks[key]


def _get_cached_positions(auth):
    with _position_cache_lock:
        now = time.monotonic()
        cached = _position_cache.get(auth)
        if cached and (now - cached["timestamp"]) < _POSITION_CACHE_TTL:
            return cached["data"]

    data = get_positions(auth)
    with _position_cache_lock:
        _position_cache[auth] = {"data": data, "timestamp": time.monotonic()}
    return data


def _invalidate_position_cache(auth):
    with _position_cache_lock:
        _position_cache.pop(auth, None)


def get_open_position(symbol, exchange, product, auth):
    try:
        pos = _get_cached_positions(auth)
        position_list = pos.get("result", {}).get("positionList", [])
        brsymbol = get_br_symbol(symbol, exchange)

        matching_position = next(
            (
                position
                for position in position_list
                if (position.get("TradingSymbol") == brsymbol or position.get("Symbol") == brsymbol)
                and position.get("ProductType") == product
            ),
            None,
        )

        return int(matching_position.get("Quantity", 0)) if matching_position else 0
    except Exception as e:
        logger.error(f"[AC Agarwal] Exception in get_open_position: {e}")
        return 0


def place_order_api(data, auth):
    """
    Places an order via AC Agarwal (Symphony XTS).
    
    Quirk #3: Client-side Freeze Quantity validation.
    Quirk #4: Lot-size validation and Synthetic Marketable Limit order calculation for MARKET orders.
    """
    try:
        AUTH_TOKEN = auth
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        quantity = int(data.get("quantity", 0))
        action = data.get("action", "BUY").upper()
        pricetype = data.get("pricetype", "LIMIT").upper()

        symbol_info = get_symbol_info(symbol, exchange) if symbol and exchange else None
        lotsize = getattr(symbol_info, "lotsize", 1) if symbol_info else 1
        tick_size = getattr(symbol_info, "tick_size", 0.05) if symbol_info else 0.05

        # Quirk #4: Lot-size validation
        if lotsize > 1 and quantity % lotsize != 0:
            error_msg = f"[AC Agarwal Safeguard] Order quantity {quantity} is not a valid multiple of lot size {lotsize} for {symbol}"
            logger.error(error_msg)
            fake_resp = httpx.Response(400, json={"type": "error", "description": error_msg})
            fake_resp.status = 400
            return fake_resp, {"error": error_msg}, None

        # Quirk #3: Client-side Freeze Quantity validation
        freeze_qty = get_freeze_qty_for_option(symbol, exchange) if symbol and exchange else 0
        if freeze_qty > 0 and quantity > freeze_qty:
            error_msg = f"[AC Agarwal Safeguard] Order quantity {quantity} exceeds client-side freeze quantity limit {freeze_qty} for {symbol}"
            logger.error(error_msg)
            fake_resp = httpx.Response(400, json={"type": "error", "description": error_msg})
            fake_resp.status = 400
            return fake_resp, {"error": error_msg}, None

        # Quirk #4: Synthetic Marketable Limit Order for MARKET orders
        if pricetype == "MARKET":
            try:
                bd = BrokerData(auth_token=auth)
                quote = bd.get_quotes(symbol, exchange)
                ltp = 0.0
                if isinstance(quote, dict) and "result" in quote:
                    ltp = float(quote["result"].get("LastTradedPrice", 0.0))

                if ltp > 0:
                    buffer_pct = 0.005  # 0.5% slippage buffer
                    raw_price = ltp * (1 + buffer_pct) if action == "BUY" else ltp * (1 - buffer_pct)
                    synthetic_price = round(round(raw_price / tick_size) * tick_size, 2)
                    data["price"] = str(synthetic_price)
                    data["pricetype"] = "LIMIT"
                    logger.info(f"[AC Agarwal Safeguard] Computed synthetic limit price {synthetic_price} from LTP {ltp} for {symbol}")
            except Exception as quote_err:
                logger.warning(f"[AC Agarwal] Failed to compute synthetic limit price: {quote_err}")

        token = get_token(symbol, exchange) if symbol and exchange else None
        newdata = transform_data(data, token)

        client = get_httpx_client()
        headers = {
            "authorization": AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        response = client.post(f"{INTERACTIVE_URL}/orders", headers=headers, json=newdata)
        response.status = response.status_code

        try:
            response_data = response.json()
        except Exception:
            response_data = {"raw_response": response.text}

        orderid = (
            response_data.get("result", {}).get("AppOrderID")
            if response_data.get("type") == "success"
            else None
        )

        return response, response_data, orderid

    except Exception as e:
        logger.error(f"[AC Agarwal] Exception in place_order_api: {e}")
        fake_resp = httpx.Response(500, json={"type": "error", "description": str(e)})
        fake_resp.status = 500
        return fake_resp, {"error": str(e)}, None


def place_smartorder_api(data, auth):
    AUTH_TOKEN = auth
    res = None
    symbol = data.get("symbol")
    exchange = data.get("exchange")
    product = data.get("product")
    symbol_lock = _get_symbol_lock(symbol, exchange, product)

    with symbol_lock:
        position_size = int(data.get("position_size", "0"))
        current_position = int(
            get_open_position(symbol, exchange, map_product_type(product), AUTH_TOKEN)
        )

        action = None
        quantity = 0

        if position_size == 0 and current_position == 0 and int(data.get("quantity", 0)) != 0:
            res, response, orderid = place_order_api(data, AUTH_TOKEN)
            _invalidate_position_cache(AUTH_TOKEN)
            return res, response, orderid

        elif position_size == current_position:
            if int(data.get("quantity", 0)) == 0:
                response = {
                    "status": "success",
                    "message": "No OpenPosition Found. Not placing Exit order.",
                }
            else:
                response = {
                    "status": "success",
                    "message": "No action needed. Position size matches current position",
                }
            return res, response, None

        if position_size == 0 and current_position > 0:
            action = "SELL"
            quantity = abs(current_position)
        elif position_size == 0 and current_position < 0:
            action = "BUY"
            quantity = abs(current_position)
        elif current_position == 0:
            action = "BUY" if position_size > 0 else "SELL"
            quantity = abs(position_size)
        else:
            if position_size > current_position:
                action = "BUY"
                quantity = position_size - current_position
            elif position_size < current_position:
                action = "SELL"
                quantity = current_position - position_size

        if action:
            order_data = data.copy()
            order_data["action"] = action
            order_data["quantity"] = str(quantity)
            res, response, orderid = place_order_api(order_data, auth)
            _invalidate_position_cache(AUTH_TOKEN)
            return res, response, orderid


def close_all_positions(current_api_key, auth):
    AUTH_TOKEN = auth
    positions_response = get_positions(AUTH_TOKEN)
    positions_list = positions_response.get("result", {}).get("positionList", [])
    if not positions_list:
        return {"message": "No Open Positions Found"}, 200

    for position in positions_list:
        if int(position.get("Quantity", 0)) == 0:
            continue

        action = "SELL" if int(position.get("Quantity", 0)) > 0 else "BUY"
        quantity = abs(int(position.get("Quantity", 0)))
        exchange_segment = position.get("ExchangeSegment")
        instrument_id = position.get("ExchangeInstrumentId")

        place_order_payload = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": instrument_id,
            "productType": position.get("ProductType"),
            "orderType": "MARKET",
            "orderSide": action,
            "timeInForce": "DAY",
            "disclosedQuantity": "0",
            "orderQuantity": str(quantity),
            "limitPrice": "0",
            "stopPrice": "0",
            "orderUniqueIdentifier": "openalgo",
        }
        res, response, orderid = place_order_api(place_order_payload, auth)

    return {"status": "success", "message": "All Open Positions SquaredOff"}, 200


def cancel_order(orderid, auth):
    AUTH_TOKEN = auth
    client = get_httpx_client()
    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    response = client.delete(f"{INTERACTIVE_URL}/orders?appOrderID={orderid}", headers=headers)
    response.status = response.status_code

    try:
        data = response.json()
    except Exception:
        data = {"status": False, "message": response.text}

    if data.get("type") == "success" or data.get("status"):
        return {"status": "success", "orderid": orderid}, 200
    else:
        return {
            "status": "error",
            "message": data.get("description") or data.get("message", "Failed to cancel order"),
        }, response.status


def modify_order(data, auth):
    AUTH_TOKEN = auth
    client = get_httpx_client()
    token = get_token(data["symbol"], data["exchange"])
    data["symbol"] = get_br_symbol(data["symbol"], data["exchange"])

    transformed_data = transform_modify_order_data(data, token)
    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    response = client.put(f"{INTERACTIVE_URL}/orders", headers=headers, json=transformed_data)
    response.status = response.status_code

    try:
        res_data = response.json()
    except Exception:
        res_data = {"status": "error", "message": response.text}

    if res_data.get("type") == "success" or res_data.get("status") == "true" or res_data.get("message") == "SUCCESS":
        orderid = res_data.get("result", {}).get("AppOrderID") or res_data.get("data", {}).get("orderid")
        return {"status": "success", "orderid": orderid}, 200
    else:
        return {
            "status": "error",
            "message": res_data.get("description") or res_data.get("message", "Failed to modify order"),
        }, response.status


def cancel_all_orders_api(data, auth):
    AUTH_TOKEN = auth
    order_book_response = get_order_book(AUTH_TOKEN)
    if order_book_response.get("type") != "success":
        return [], []

    orders = order_book_response.get("result", [])
    orders_to_cancel = [
        order for order in orders if order.get("OrderStatus") in ["New", "Trigger Pending", "NEW", "TRIGGER_PENDING"]
    ]

    canceled_orders = []
    failed_cancellations = []

    for order in orders_to_cancel:
        orderid = order.get("AppOrderID")
        if orderid:
            cancel_response, status_code = cancel_order(orderid, auth)
            if status_code == 200:
                canceled_orders.append(orderid)
            else:
                failed_cancellations.append(orderid)

    return canceled_orders, failed_cancellations
