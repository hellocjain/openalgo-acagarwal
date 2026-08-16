"""AC Agarwal (Symphony XTS) broker base URLs configuration."""

import os

BASE_URL = os.getenv("ACAGARWAL_BASE_URL", "https://symphony.acagarwal.com:3000").rstrip("/")

INTERACTIVE_URL = f"{BASE_URL}/interactive"
MARKET_DATA_URL = f"{BASE_URL}/apimarketdata"
