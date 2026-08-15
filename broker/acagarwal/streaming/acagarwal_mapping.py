# broker/acagarwal/streaming/acagarwal_mapping.py

import logging


class ACAgarwalExchangeMapper:
    """Maps between OpenAlgo exchange codes and AC Agarwal (Symphony XTS) specific exchange types"""

    EXCHANGE_TYPES = {
        "NSE": 1,
        "NFO": 2,
        "NSE_INDEX": 1,
        "CDS": 3,
        "BSE": 11,
        "BFO": 12,
        "BSE_INDEX": 11,
        "MCX": 51,
        "NSECM": 1,
        "NSEFO": 2,
        "NSECD": 3,
        "BSECM": 11,
        "BSEFO": 12,
        "MCXFO": 51,
    }

    REVERSE_EXCHANGE_TYPES = {
        1: "NSE",
        2: "NFO",
        3: "CDS",
        11: "BSE",
        12: "BFO",
        51: "MCX",
    }

    @staticmethod
    def get_exchange_type(exchange):
        if exchange is None:
            logging.warning("Exchange is None, defaulting to NSE (1)")
            return 1

        exchange = str(exchange).upper().strip()
        all_exchange_mappings = {
            "NSE": 1,
            "NFO": 2,
            "CDS": 3,
            "BSE": 11,
            "BFO": 12,
            "MCX": 51,
            "NSECM": 1,
            "NSEFO": 2,
            "NSECD": 3,
            "BSECM": 11,
            "BSEFO": 12,
            "MCXFO": 51,
            "NSE_INDEX": 1,
            "BSE_INDEX": 11,
            "1": 1,
            "2": 2,
            "3": 3,
            "11": 11,
            "12": 12,
            "51": 51,
        }

        exchange_code = all_exchange_mappings.get(exchange)
        if exchange_code is not None:
            logging.info(f"[AC Agarwal] Mapped exchange '{exchange}' to code {exchange_code}")
            return exchange_code

        logging.warning(f"[AC Agarwal] Unknown exchange '{exchange}', defaulting to NSE (1)")
        return 1

    @staticmethod
    def get_openalgo_exchange(acagarwal_code):
        return ACAgarwalExchangeMapper.REVERSE_EXCHANGE_TYPES.get(acagarwal_code, "NSE")


class ACAgarwalCapabilityRegistry:
    exchanges = ["NSE", "NFO", "CDS", "BSE", "BFO", "MCX"]
    subscription_modes = [1, 2, 3]
    depth_support = {
        "NSE": [5, 20],
        "NFO": [5, 20],
        "CDS": [5],
        "BSE": [5],
        "BFO": [5],
        "MCX": [5],
    }

    @classmethod
    def get_supported_depth_levels(cls, exchange):
        return cls.depth_support.get(exchange, [5])

    @classmethod
    def is_depth_level_supported(cls, exchange, depth_level):
        supported_depths = cls.get_supported_depth_levels(exchange)
        return depth_level in supported_depths

    @classmethod
    def get_fallback_depth_level(cls, exchange, requested_depth):
        supported_depths = cls.get_supported_depth_levels(exchange)
        fallbacks = [d for d in supported_depths if d <= requested_depth]
        if fallbacks:
            return max(fallbacks)
        return 5
