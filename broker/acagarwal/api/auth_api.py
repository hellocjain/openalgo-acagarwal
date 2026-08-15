import os
import httpx

from broker.acagarwal.baseurl import BASE_URL, INTERACTIVE_URL
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def authenticate_broker(request_token=None):
    """
    Authenticates interactive and market data sessions for AC Agarwal (Symphony XTS).
    
    Quirk 1: Interactive login request's "source" field MUST be "WEBAPI" (all caps).
    Quirk 2: Market data login tries multiple endpoint paths with short timeout fallback.
    """
    try:
        client = get_httpx_client()
        BROKER_API_KEY = os.getenv("BROKER_API_KEY")
        BROKER_API_SECRET = os.getenv("BROKER_API_SECRET")

        if not BROKER_API_KEY or not BROKER_API_SECRET:
            return None, None, None, "Missing BROKER_API_KEY or BROKER_API_SECRET in environment"

        # Quirk 1: source must be literal string "WEBAPI" (all caps)
        payload = {
            "appKey": BROKER_API_KEY,
            "secretKey": BROKER_API_SECRET,
            "source": "WEBAPI",
        }

        headers = {"Content-Type": "application/json"}
        session_url = f"{INTERACTIVE_URL}/user/session"

        response = client.post(session_url, json=payload, headers=headers)

        if response.status_code == 200:
            result = response.json()
            if result.get("type") == "success":
                token = result["result"]["token"]
                logger.info(f"[AC Agarwal] Interactive Auth Token obtained successfully")

                # Fetch market data feed token
                feed_token, user_id, feed_error = get_feed_token()
                if feed_error:
                    return token, None, None, f"Feed token error: {feed_error}"

                return token, feed_token, user_id, None
            else:
                return (
                    None,
                    None,
                    None,
                    f"Authentication failed: {result.get('description', 'No access token returned')}",
                )
        else:
            try:
                error_detail = response.json()
                error_message = error_detail.get("description") or error_detail.get("message", "Authentication failed")
            except Exception:
                error_message = response.text
            return None, None, None, f"API error ({response.status_code}): {error_message}"

    except Exception as e:
        return None, None, None, f"Error during AC Agarwal authentication: {str(e)}"


def get_feed_token():
    """
    Fetches Market Data feed token for AC Agarwal.
    
    Quirk 2: Market-data login needs a fallback across multiple URL paths:
    1. /apimarketdata/auth/login
    2. /apibinarymarketdata/auth/login
    3. /marketdata/auth/login
    First success wins.
    """
    try:
        BROKER_API_KEY_MARKET = os.getenv("BROKER_API_KEY_MARKET")
        BROKER_API_SECRET_MARKET = os.getenv("BROKER_API_SECRET_MARKET")

        if not BROKER_API_KEY_MARKET or not BROKER_API_SECRET_MARKET:
            return None, None, "Missing BROKER_API_KEY_MARKET or BROKER_API_SECRET_MARKET in environment"

        # Quirk 1: source must be literal string "WEBAPI" (all caps)
        feed_payload = {
            "appKey": BROKER_API_KEY_MARKET,
            "secretKey": BROKER_API_SECRET_MARKET,
            "source": "WEBAPI",
        }

        feed_headers = {"Content-Type": "application/json"}
        client = get_httpx_client()

        # Quirk 2: List of candidate paths to attempt for market data login
        candidate_paths = [
            "/apimarketdata/auth/login",
            "/apibinarymarketdata/auth/login",
            "/marketdata/auth/login",
        ]

        last_error = "No market data auth endpoint answered"
        for path in candidate_paths:
            feed_url = f"{BASE_URL}{path}"
            try:
                logger.info(f"[AC Agarwal] Attempting market data login at: {feed_url}")
                feed_response = client.post(feed_url, json=feed_payload, headers=feed_headers, timeout=5.0)

                if feed_response.status_code == 200:
                    feed_result = feed_response.json()
                    if feed_result.get("type") == "success":
                        feed_token = feed_result["result"].get("token")
                        user_id = feed_result["result"].get("userID")
                        logger.info(f"[AC Agarwal] Market Data Feed Token obtained successfully via {path}")
                        return feed_token, user_id, None
                    else:
                        last_error = feed_result.get("description") or "Market data login rejected"
                else:
                    last_error = f"HTTP {feed_response.status_code} at {path}"
            except Exception as req_err:
                logger.warning(f"[AC Agarwal] Market data login attempt failed at {path}: {str(req_err)}")
                last_error = str(req_err)

        return None, None, f"Market Data Auth failed on all candidate endpoints: {last_error}"

    except Exception as e:
        return None, None, f"Exception in get_feed_token: {str(e)}"
