# broker/acagarwal/api/funds.py

import os
from broker.acagarwal.baseurl import INTERACTIVE_URL
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def get_margin_data(auth_token):
    if not auth_token:
        logger.warning("[AC Agarwal Funds] get_margin_data called with empty/None auth_token")
        return {}
    try:
        client = get_httpx_client()
        headers = {"authorization": auth_token, "Content-Type": "application/json"}
        url = f"{INTERACTIVE_URL}/user/balance"
        token_prefix = auth_token[:15] if auth_token else "NONE"
        logger.info(f"[AC Agarwal Funds] Requesting balance at {url} with auth token: {token_prefix}...")

        response = client.get(url, headers=headers)
        logger.info(f"[AC Agarwal Funds] Response HTTP status: {response.status_code}")

        # If token expired or invalid (HTTP 400/401), attempt automatic session re-authentication
        if response.status_code in (400, 401):
            logger.warning("[AC Agarwal Funds] Token expired or invalid, attempting automatic re-authentication...")
            from broker.acagarwal.api.auth_api import authenticate_broker
            new_auth, new_feed, user_id, err = authenticate_broker("acagarwal")
            if new_auth and not err:
                headers["authorization"] = new_auth
                response = client.get(url, headers=headers)
                logger.info(f"[AC Agarwal Funds] Post-reauth balance HTTP status: {response.status_code}")
                # Save refreshed token into DB
                try:
                    from database.auth_db import upsert_auth
                    from flask import session
                    user = session.get("user", "admin")
                    upsert_auth(user, new_auth, "acagarwal", feed_token=new_feed, user_id=user_id)
                except Exception as save_err:
                    logger.warning(f"[AC Agarwal Funds] Failed to save refreshed auth token: {save_err}")

        if response.status_code != 200:
            return {}

        margin_data = response.json()

        if (
            margin_data.get("result")
            and margin_data["result"].get("BalanceList")
            and margin_data["result"]["BalanceList"]
        ):
            rms_sublimits = margin_data["result"]["BalanceList"][0].get("limitObject", {}).get("RMSSubLimits", {})

            res_dict = {
                "availablecash": f"{float(rms_sublimits.get('netMarginAvailable', 0)):.2f}",
                "collateral": f"{float(rms_sublimits.get('collateral', 0)):.2f}",
                "m2munrealized": f"{float(rms_sublimits.get('UnrealizedMTM', 0)):.2f}",
                "m2mrealized": f"{float(rms_sublimits.get('RealizedMTM', 0)):.2f}",
                "utiliseddebits": f"{float(rms_sublimits.get('marginUtilized', 0)):.2f}",
            }
            logger.info(f"[AC Agarwal Funds] Parsed margin dict: {res_dict}")
            return res_dict

        logger.warning(f"[AC Agarwal Funds] Missing BalanceList in result: {margin_data}")
        return {}

    except Exception as e:
        logger.error(f"[AC Agarwal Funds] Exception in get_margin_data: {e}", exc_info=True)
        return {}
