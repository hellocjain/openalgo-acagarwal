# broker/acagarwal/api/data.py

import json
import os
import urllib.parse
from datetime import datetime

import pandas as pd
from broker.acagarwal.baseurl import BASE_URL, MARKET_DATA_URL
from database.token_db import get_br_symbol, get_brexchange, get_token, get_tokens_bulk
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


class BrokerData:
    def __init__(self, auth_token, feed_token=None, user_id=None):
        self.auth_token = auth_token
        self.feed_token = feed_token
        self.user_id = user_id

        self.timeframe_map = {
            "1m": "1MIN",
            "5m": "5MIN",
            "15m": "15MIN",
            "30m": "30MIN",
            "60m": "60MIN",
            "D": "1DAY",
        }

    def _get_headers(self):
        token = self.feed_token or self.auth_token or ""
        return {
            "authorization": token,
            "Content-Type": "application/json",
        }

    def get_quotes(self, symbol, exchange):
        try:
            client = get_httpx_client()
            token = get_token(symbol, exchange)
            brexchange = get_brexchange(symbol, exchange)

            url = f"{MARKET_DATA_URL}/instruments/quotes"
            payload = {
                "instruments": [
                    {
                        "exchangeSegment": map_exchange_code(exchange),
                        "exchangeInstrumentID": token,
                    }
                ],
                "xtsMessageCode": 1502,
                "publishFormat": "JSON",
            }

            response = client.post(url, json=payload, headers=self._get_headers())
            if response.status_code == 200:
                data = response.json()
                return data
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"[AC Agarwal] Error fetching quotes: {e}")
            return {"status": "error", "message": str(e)}

    def get_depth(self, symbol, exchange):
        try:
            client = get_httpx_client()
            token = get_token(symbol, exchange)

            url = f"{MARKET_DATA_URL}/instruments/quotes"
            payload = {
                "instruments": [
                    {
                        "exchangeSegment": map_exchange_code(exchange),
                        "exchangeInstrumentID": token,
                    }
                ],
                "xtsMessageCode": 1502,
                "publishFormat": "JSON",
            }

            response = client.post(url, json=payload, headers=self._get_headers())
            if response.status_code == 200:
                return response.json()
            return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"[AC Agarwal] Error fetching depth: {e}")
            return {"status": "error", "message": str(e)}

    def get_history(self, symbol, exchange, interval, start_date, end_date):
        try:
            client = get_httpx_client()
            token = get_token(symbol, exchange)

            if not token:
                logger.warning(f"[AC Agarwal] Could not find token for {exchange}:{symbol}")
                return pd.DataFrame()

            segment_map = {
                "NSE": "NSECM",
                "BSE": "BSECM",
                "NFO": "NSEFO",
                "BFO": "BSEFO",
                "CDS": "NSECD",
                "MCX": "MCXFO",
            }
            exchange_segment = segment_map.get(exchange, "NSECM")

            compression_map = {
                "1m": "60",
                "2m": "120",
                "3m": "180",
                "5m": "300",
                "10m": "600",
                "15m": "900",
                "30m": "1800",
                "60m": "3600",
                "D": "D",
            }
            compression_value = compression_map.get(interval, "300")

            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            from_str = start_dt.strftime("%b %d %Y 000000")
            to_str = end_dt.strftime("%b %d %Y 235959")

            params = {
                "exchangeSegment": exchange_segment,
                "exchangeInstrumentID": token,
                "startTime": from_str,
                "endTime": to_str,
                "compressionValue": compression_value,
            }

            url = f"{MARKET_DATA_URL}/instruments/ohlc"
            response = client.get(url, params=params, headers=self._get_headers())

            if response.status_code == 200:
                res = response.json()
                if res.get("type") == "success":
                    result = res.get("result", {})
                    raw_data = result.get("dataReponse") or result.get("dataResponse") or result.get("data", "")
                    if isinstance(raw_data, str) and raw_data.strip():
                        rows = raw_data.strip().split(",")
                        parsed_bars = []
                        for row in rows:
                            fields = row.split("|")
                            if len(fields) >= 6:
                                try:
                                    parsed_bars.append({
                                        "timestamp": int(fields[0]),
                                        "open": float(fields[1]),
                                        "high": float(fields[2]),
                                        "low": float(fields[3]),
                                        "close": float(fields[4]),
                                        "volume": int(fields[5]),
                                    })
                                except (ValueError, IndexError):
                                    continue
                        if parsed_bars:
                            return pd.DataFrame(parsed_bars)
                    elif isinstance(raw_data, list) and len(raw_data) > 0:
                        return pd.DataFrame(raw_data)

            return pd.DataFrame()
        except Exception as e:
            logger.error(f"[AC Agarwal] Error fetching history: {e}")
            return pd.DataFrame()


def map_exchange_code(exchange):
    mapping = {
        "NSE": 1,
        "NFO": 2,
        "CDS": 3,
        "BSE": 11,
        "BFO": 12,
        "MCX": 51,
    }
    return mapping.get(exchange, 1)
