# broker/acagarwal/mapping/transform_data.py

from database.token_db import get_br_symbol
from utils.logging import get_logger

logger = get_logger(__name__)


def transform_data(data, token):
    """
    Transforms standard OpenAlgo API request into AC Agarwal (Symphony XTS) payload.
    """
    transformed = {
        "exchangeSegment": map_exchange(data["exchange"]),
        "exchangeInstrumentID": token,
        "productType": map_product_type(data["product"]),
        "orderType": map_order_type(data["pricetype"]),
        "orderSide": data["action"].upper(),
        "timeInForce": "DAY",
        "disclosedQuantity": str(data.get("disclosed_quantity", "0")),
        "orderQuantity": int(data["quantity"]),
        "limitPrice": str(data.get("price", "0")),
        "stopPrice": str(data.get("trigger_price", "0")),
        "orderUniqueIdentifier": "openalgo",
    }
    logger.info(f"[AC Agarwal] Transformed order payload: {transformed}")
    return transformed


def transform_modify_order_data(data, token):
    """
    Transforms OpenAlgo order modification payload into Symphony XTS structure.
    """
    return {
        "appOrderID": str(data["orderid"]),
        "modifiedProductType": map_product_type(data["product"]),
        "modifiedOrderType": map_order_type(data["pricetype"]),
        "modifiedOrderQuantity": int(data["quantity"]),
        "modifiedDisclosedQuantity": str(data.get("disclosed_quantity", "0")),
        "modifiedLimitPrice": str(data["price"]),
        "modifiedStopPrice": str(data.get("trigger_price", "0")),
        "modifiedTimeInForce": "DAY",
        "orderUniqueIdentifier": "openalgo",
    }


def map_exchange(exchange):
    exchange_mapping = {
        "NSE": "NSECM",
        "BSE": "BSECM",
        "MCX": "MCXFO",
        "NFO": "NSEFO",
        "BFO": "BSEFO",
        "CDS": "NSECD",
    }
    return exchange_mapping.get(exchange, exchange)


def map_order_type(pricetype):
    order_type_mapping = {
        "MARKET": "MARKET",
        "LIMIT": "LIMIT",
        "SL": "STOPLIMIT",
        "SL-M": "STOPMARKET",
    }
    return order_type_mapping.get(pricetype, "MARKET")


def map_product_type(product):
    product_mapping = {
        "MIS": "MIS",
        "NRML": "NRML",
        "CNC": "CNC",
    }
    return product_mapping.get(product, "NRML")


def reverse_map_product_type(product_type):
    reverse_mapping = {
        "MIS": "MIS",
        "NRML": "NRML",
        "CNC": "CNC",
    }
    return reverse_mapping.get(product_type, product_type)
