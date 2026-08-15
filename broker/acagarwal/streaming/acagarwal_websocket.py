# broker/acagarwal/streaming/acagarwal_websocket.py

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests
import socketio
from broker.acagarwal.baseurl import BASE_URL, INTERACTIVE_URL, MARKET_DATA_URL

logger = logging.getLogger(__name__)


class ACAgarwalWebSocketClient:
    """
    AC Agarwal (Symphony XTS) Socket.IO client for market data streaming.
    """

    BASE_URL = BASE_URL
    SOCKET_PATH = "/apimarketdata/socket.io"
    API_BASE_URL = f"{MARKET_DATA_URL}/instruments/subscription"

    SUBSCRIBE_ACTION = 1
    UNSUBSCRIBE_ACTION = 0

    LTP_MODE = 1
    QUOTE_MODE = 2
    DEPTH_MODE = 3

    def __init__(self, api_key: str, api_secret: str, user_id: str, base_url: str = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.user_id = user_id
        self.base_url = base_url or self.BASE_URL

        self.token = None
        self.sio = None
        self.connected = False
        self.subscribed_instruments = {}

        self.on_connect_callback = None
        self.on_disconnect_callback = None
        self.on_tick_callback = None
        self.on_order_update_callback = None
        self.on_error_callback = None

        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.running = False
        self.lock = threading.Lock()

    def _login(self) -> bool:
        try:
            url = f"{MARKET_DATA_URL}/auth/login"
            payload = {
                "appKey": self.api_key,
                "secretKey": self.api_secret,
                "source": "WEBAPI",
            }
            headers = {"Content-Type": "application/json"}

            logger.info(f"[AC Agarwal WS] Logging in to Market Data API at: {url}")
            response = requests.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("type") == "success":
                    self.token = data["result"].get("token")
                    logger.info("[AC Agarwal WS] Market Data login successful")
                    return True
                else:
                    logger.error(f"[AC Agarwal WS] Login failed: {data.get('description')}")
                    return False
            else:
                logger.error(f"[AC Agarwal WS] Login HTTP error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[AC Agarwal WS] Login exception: {e}")
            return False

    def connect(self) -> bool:
        with self.lock:
            if self.connected:
                return True

            if not self.token:
                if not self._login():
                    return False

            try:
                self.sio = socketio.Client(
                    reconnection=True,
                    reconnection_attempts=self.max_reconnect_attempts,
                    reconnection_delay=self.reconnect_delay,
                    reconnection_delay_max=self.max_reconnect_delay,
                    logger=False,
                    engineio_logger=False,
                )

                self._register_events()

                ws_url = f"{self.base_url}?token={self.token}&userID={self.user_id}&source=WEBAPI"
                logger.info(f"[AC Agarwal WS] Connecting Socket.IO client...")
                self.sio.connect(ws_url, socketio_path=self.SOCKET_PATH, transports=["websocket"])

                self.running = True
                return True
            except Exception as e:
                logger.error(f"[AC Agarwal WS] Socket.IO connection failed: {e}")
                self.connected = False
                return False

    def disconnect(self):
        with self.lock:
            self.running = False
            if self.sio and self.connected:
                try:
                    self.sio.disconnect()
                except Exception as e:
                    logger.error(f"[AC Agarwal WS] Error disconnecting: {e}")
            self.connected = False

    def _register_events(self):
        @self.sio.on("connect")
        def on_connect():
            logger.info("[AC Agarwal WS] Socket.IO connected")
            self.connected = True
            if self.on_connect_callback:
                self.on_connect_callback()

        @self.sio.on("disconnect")
        def on_disconnect():
            logger.info("[AC Agarwal WS] Socket.IO disconnected")
            self.connected = False
            if self.on_disconnect_callback:
                self.on_disconnect_callback()

        @self.sio.on("1501-json-full")
        @self.sio.on("1502-json-full")
        @self.sio.on("1505-json-full")
        @self.sio.on("1507-json-full")
        @self.sio.on("1510-json-full")
        @self.sio.on("1512-json-full")
        def on_market_data(data):
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                if self.on_tick_callback:
                    self.on_tick_callback(data)
            except Exception as e:
                logger.error(f"[AC Agarwal WS] Error processing tick: {e}")

        @self.sio.on("1105-json-full")
        def on_order_update(data):
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                if self.on_order_update_callback:
                    self.on_order_update_callback(data)
            except Exception as e:
                logger.error(f"[AC Agarwal WS] Error processing order update: {e}")

    def subscribe(self, instruments: List[Dict[str, Any]], mode: int = 2) -> bool:
        if not self.connected or not self.token:
            logger.error("[AC Agarwal WS] Cannot subscribe - client disconnected")
            return False

        try:
            url = self.API_BASE_URL
            payload = {
                "instruments": instruments,
                "xtsMessageCode": 1502 if mode == 2 else (1505 if mode == 3 else 1501),
            }
            headers = {
                "authorization": self.token,
                "Content-Type": "application/json",
            }
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"[AC Agarwal WS] Subscription exception: {e}")
            return False
