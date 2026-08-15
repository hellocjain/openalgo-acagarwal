# broker/acagarwal/streaming/acagarwal_adapter.py

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from broker.acagarwal.streaming.acagarwal_mapping import ACAgarwalCapabilityRegistry, ACAgarwalExchangeMapper
from broker.acagarwal.streaming.acagarwal_websocket import ACAgarwalWebSocketClient
from database.auth_db import get_auth_token, get_feed_token
from database.token_db import get_symbol
from websocket_proxy.base_adapter import BaseBrokerWebSocketAdapter

logger = logging.getLogger(__name__)


class ACAgarwalWebSocketAdapter(BaseBrokerWebSocketAdapter):
    """
    AC Agarwal (Symphony XTS) specific implementation of the WebSocket adapter.
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("acagarwal_websocket")
        self.ws_client = None
        self.user_id = None
        self.broker_name = "acagarwal"
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.running = False
        self.lock = threading.Lock()

    def initialize(
        self, broker_name: str, user_id: str, auth_data: dict[str, str] | None = None
    ) -> None:
        self.user_id = user_id
        self.broker_name = broker_name

        if not auth_data:
            auth_token = get_auth_token(user_id, bypass_cache=True)
            feed_token = get_feed_token(user_id)

            api_key = os.getenv("BROKER_API_KEY_MARKET") or os.getenv("BROKER_API_KEY")
            api_secret = os.getenv("BROKER_API_SECRET_MARKET") or os.getenv("BROKER_API_SECRET")

            if not api_key or not api_secret:
                raise ValueError("Missing AC Agarwal API credentials in environment variables")

        self.ws_client = ACAgarwalWebSocketClient(
            api_key=api_key,
            api_secret=api_secret,
            user_id=user_id,
        )

        self.ws_client.on_tick_callback = self._handle_tick
        self.ws_client.on_order_update_callback = self._handle_order_update
        self.running = True

    def connect(self) -> bool:
        if self.ws_client:
            return self.ws_client.connect()
        return False

    def disconnect(self) -> None:
        if self.ws_client:
            self.ws_client.disconnect()
        self.running = False

    def _handle_tick(self, raw_tick: dict):
        try:
            parsed = self.transform_to_openalgo_format(raw_tick)
            if parsed:
                self.publish_tick(parsed)
        except Exception as e:
            self.logger.error(f"[AC Agarwal WS] Tick handler error: {e}")

    def _handle_order_update(self, raw_update: dict):
        try:
            self.publish_order_update(raw_update)
        except Exception as e:
            self.logger.error(f"[AC Agarwal WS] Order update handler error: {e}")

    def transform_to_openalgo_format(self, raw_data: Any) -> Dict[str, Any]:
        try:
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)

            token = str(raw_data.get("ExchangeInstrumentID", ""))
            exch_code = raw_data.get("ExchangeSegment", 1)
            exchange = ACAgarwalExchangeMapper.get_openalgo_exchange(exch_code)
            symbol = get_symbol(token, exchange) or token

            return {
                "type": "quote",
                "symbol": symbol,
                "token": token,
                "exchange": exchange,
                "ltp": float(raw_data.get("LastTradedPrice", 0.0)),
                "open": float(raw_data.get("Open", 0.0)),
                "high": float(raw_data.get("High", 0.0)),
                "low": float(raw_data.get("Low", 0.0)),
                "close": float(raw_data.get("Close", 0.0)),
                "volume": int(raw_data.get("Volume", 0)),
            }
        except Exception as e:
            self.logger.error(f"[AC Agarwal WS] Error transforming data: {e}")
            return {}


# Class name alias expected by broker_factory capitalization logic
AcagarwalWebSocketAdapter = ACAgarwalWebSocketAdapter
