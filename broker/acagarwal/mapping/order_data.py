# broker/acagarwal/mapping/order_data.py

import json
from database.token_db import get_oa_symbol, get_symbol
from utils.logging import get_logger

logger = get_logger(__name__)


def map_order_data(order_data):
    exchange_mapping = {
        "NSECM": "NSE",
        "BSECM": "BSE",
        "NSEFO": "NFO",
        "BSEFO": "BFO",
        "MCXFO": "MCX",
        "NSECD": "CDS",
    }

    if not order_data or "result" not in order_data or not order_data["result"]:
        logger.info("[AC Agarwal] No order data available.")
        return []

    order_list = order_data["result"]
    if isinstance(order_list, list):
        for order in order_list:
            symboltoken = order.get("ExchangeInstrumentID")
            exch = order.get("ExchangeSegment", "")
            exchange = exchange_mapping.get(exch, exch)

            symbol_from_db = get_symbol(symboltoken, exchange)
            if symbol_from_db:
                order["TradingSymbol"] = symbol_from_db

    return order_list


def calculate_order_statistics(order_data):
    total_buy_orders = total_sell_orders = 0
    total_completed_orders = total_open_orders = total_rejected_orders = 0

    if order_data:
        for order in order_data:
            if order.get("OrderSide") == "BUY":
                total_buy_orders += 1
            elif order.get("OrderSide") == "SELL":
                total_sell_orders += 1

            status = order.get("OrderStatus")
            if status in ["Filled", "FILLED"]:
                total_completed_orders += 1
            elif status in ["New", "NEW", "Trigger Pending"]:
                total_open_orders += 1
            elif status in ["Rejected", "REJECTED"]:
                total_rejected_orders += 1

    return {
        "total_buy_orders": total_buy_orders,
        "total_sell_orders": total_sell_orders,
        "total_completed_orders": total_completed_orders,
        "total_open_orders": total_open_orders,
        "total_rejected_orders": total_rejected_orders,
    }


def transform_order_data(orders):
    if isinstance(orders, dict):
        orders = [orders]
    elif not isinstance(orders, list):
        return []

    transformed_orders = []
    exchange_mapping = {
        "NSECM": "NSE",
        "BSECM": "BSE",
        "NSEFO": "NFO",
        "BSEFO": "BFO",
        "MCXFO": "MCX",
        "NSECD": "CDS",
    }
    order_type_mapping = {
        "Limit": "LIMIT",
        "Market": "MARKET",
        "StopLimit": "SL",
        "StopMarket": "SL-M",
    }
    order_status_mapping = {
        "Filled": "complete",
        "Rejected": "rejected",
        "Cancelled": "cancelled",
        "New": "open",
    }

    for order in orders:
        if not isinstance(order, dict):
            continue
        exchange = order.get("ExchangeSegment", "")
        mapped_exchange = exchange_mapping.get(exchange, exchange)

        order_type = order.get("OrderType", "")
        mapped_order_type = order_type_mapping.get(order_type, order_type)

        order_status = order.get("OrderStatus", "")
        mapped_order_status = order_status_mapping.get(order_status, order_status)

        transformed_order = {
            "symbol": order.get("TradingSymbol", ""),
            "exchange": mapped_exchange,
            "action": order.get("OrderSide", ""),
            "quantity": order.get("OrderQuantity", 0),
            "price": order.get("OrderPrice", 0.0),
            "trigger_price": order.get("OrderStopPrice", 0.0),
            "pricetype": mapped_order_type,
            "product": order.get("ProductType", ""),
            "orderid": str(int(float(order.get("AppOrderID", 0) or 0))),
            "order_status": mapped_order_status,
            "timestamp": order.get("LastUpdateDateTime", ""),
        }
        transformed_orders.append(transformed_order)

    return transformed_orders


def map_trade_data(trade_data):
    exchange_mapping = {
        "NSECM": "NSE",
        "BSECM": "BSE",
        "NSEFO": "NFO",
        "BSEFO": "BFO",
        "MCXFO": "MCX",
        "NSECD": "CDS",
    }

    if not trade_data or "result" not in trade_data or not trade_data["result"]:
        return []

    trade_list = trade_data["result"]
    if isinstance(trade_list, list):
        for trade in trade_list:
            symboltoken = trade.get("ExchangeInstrumentID")
            exch = trade.get("ExchangeSegment", "")
            exchange = exchange_mapping.get(exch, exch)

            symbol_from_db = get_symbol(symboltoken, exchange)
            if symbol_from_db:
                trade["TradingSymbol"] = symbol_from_db

    return trade_list


def transform_tradebook_data(tradebook_data):
    transformed_data = []
    exchange_mapping = {
        "NSECM": "NSE",
        "BSECM": "BSE",
        "NSEFO": "NFO",
        "BSEFO": "BFO",
        "MCXFO": "MCX",
        "NSECD": "CDS",
    }

    if not isinstance(tradebook_data, list):
        return transformed_data

    for trade in tradebook_data:
        exchange = trade.get("ExchangeSegment", "")
        mapped_exchange = exchange_mapping.get(exchange, exchange)

        quantity = int(trade.get("OrderQuantity", 0))
        average_price = float(trade.get("OrderAverageTradedPrice", 0.0))

        transformed_trade = {
            "symbol": trade.get("TradingSymbol", ""),
            "exchange": mapped_exchange,
            "product": trade.get("ProductType", ""),
            "action": trade.get("OrderSide", ""),
            "quantity": quantity,
            "average_price": average_price,
            "trade_value": quantity * average_price,
            "orderid": str(int(float(trade.get("AppOrderID", 0) or 0))),
            "timestamp": trade.get("OrderGeneratedDateTime", ""),
        }
        transformed_data.append(transformed_trade)
    return transformed_data


def map_position_data(position_data):
    if not position_data or "result" not in position_data or not position_data["result"]:
        return []
    return position_data["result"]


def transform_positions_data(positions_data):
    if isinstance(positions_data, dict):
        positions_data = positions_data.get("positionList", [])
    transformed_data = []
    exchange_mapping = {
        "NSECM": "NSE",
        "BSECM": "BSE",
        "NSEFO": "NFO",
        "BSEFO": "BFO",
        "MCXFO": "MCX",
        "NSECD": "CDS",
    }

    if not isinstance(positions_data, list):
        return transformed_data

    for position in positions_data:
        if not isinstance(position, dict):
            continue
        symboltoken = position.get("ExchangeInstrumentId")
        exchange = position.get("ExchangeSegment", "")
        mapped_exchange = exchange_mapping.get(exchange, exchange)

        symbol_from_db = get_symbol(symboltoken, mapped_exchange)
        if symbol_from_db:
            position["TradingSymbol"] = symbol_from_db

        netqty = float(position.get("Quantity", 0))
        if netqty > 0:
            net_amount = float(position.get("BuyAveragePrice", 0))
        elif netqty < 0:
            net_amount = float(position.get("SellAveragePrice", 0))
        else:
            net_amount = 0

        average_price_formatted = f"{net_amount:.2f}"

        transformed_position = {
            "symbol": position.get("TradingSymbol", ""),
            "exchange": mapped_exchange,
            "product": position.get("ProductType", ""),
            "quantity": position.get("Quantity", 0),
            "average_price": average_price_formatted,
            "ltp": position.get("ltp", 0.0),
            "pnl": position.get("pnl", 0.0),
        }
        transformed_data.append(transformed_position)
    return transformed_data


def map_portfolio_data(portfolio_data):
    if not portfolio_data or portfolio_data.get("type") != "success" or "result" not in portfolio_data:
        return {"holdings": [], "totalholding": None}

    result = portfolio_data["result"]
    rms_holdings = result.get("RMSHoldings", {})
    holdings_data = rms_holdings.get("Holdings", {})

    holdings_list = []
    total_holding_value = 0
    total_inv_value = 0
    total_pnl = 0

    for isin, holding in holdings_data.items():
        nse_instrument_id = holding.get("ExchangeNSEInstrumentId")
        exchange = "NSE"

        trading_symbol = get_symbol(nse_instrument_id, exchange) or isin
        quantity = holding.get("HoldingQuantity", 0)
        buy_avg_price = holding.get("BuyAvgPrice", 0)
        inv_value = quantity * buy_avg_price

        holding_entry = {
            "tradingsymbol": trading_symbol,
            "exchange": exchange,
            "quantity": quantity,
            "product": "CNC",
            "buy_price": buy_avg_price,
            "investment_value": inv_value,
            "current_value": inv_value,
            "profitandloss": 0,
            "pnlpercentage": 0,
        }
        holdings_list.append(holding_entry)
        total_inv_value += inv_value
        total_holding_value += inv_value

    totalholding = {
        "totalholdingvalue": total_holding_value,
        "totalinvvalue": total_inv_value,
        "totalprofitandloss": total_pnl,
        "totalpnlpercentage": 0 if total_inv_value == 0 else (total_pnl / total_inv_value) * 100,
    }

    return {"holdings": holdings_list, "totalholding": totalholding}


def transform_holdings_data(holdings_data):
    transformed_data = []
    if not holdings_data or "holdings" not in holdings_data:
        return transformed_data

    for holdings in holdings_data["holdings"]:
        transformed_position = {
            "symbol": holdings.get("tradingsymbol", ""),
            "exchange": holdings.get("exchange", ""),
            "quantity": holdings.get("quantity", 0),
            "product": holdings.get("product", ""),
            "pnl": holdings.get("profitandloss", 0.0),
            "pnlpercent": holdings.get("pnlpercentage", 0.0),
        }
        transformed_data.append(transformed_position)

    return transformed_data


def calculate_portfolio_statistics(holdings_data):
    if "totalholding" not in holdings_data or holdings_data["totalholding"] is None:
        return {
            "totalholdingvalue": 0,
            "totalinvvalue": 0,
            "totalprofitandloss": 0,
            "totalpnlpercentage": 0,
        }
    totalholding = holdings_data["totalholding"]
    return {
        "totalholdingvalue": totalholding.get("totalholdingvalue", 0),
        "totalinvvalue": totalholding.get("totalinvvalue", 0),
        "totalprofitandloss": totalholding.get("totalprofitandloss", 0),
        "totalpnlpercentage": totalholding.get("totalpnlpercentage", 0),
    }
