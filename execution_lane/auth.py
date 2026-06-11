import logging
import time

import pyotp
from SmartApi import SmartConnect

from config import API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET

logging.getLogger("SmartApi.smartConnect").setLevel(logging.CRITICAL)
logging.getLogger("SmartApi").setLevel(logging.CRITICAL)

_MAX_RETRIES = 3
_RETRY_DELAY = 20   # seconds between retries


def get_session() -> SmartConnect:
    """Fresh login with retry on network timeout. SmartAPI invalidates prior
    tokens on new login so cross-process caching is unreliable."""
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            obj       = SmartConnect(api_key=API_KEY)
            totp_code = pyotp.TOTP(TOTP_SECRET).now()
            resp      = obj.generateSession(CLIENT_ID, PASSWORD, totp_code)
            if resp and resp.get("status"):
                return obj
            last_err = f"SmartAPI login failed: {resp}"
        except Exception as e:
            last_err = str(e)
        if attempt < _MAX_RETRIES:
            print(f"  [auth] attempt {attempt} failed — retrying in {_RETRY_DELAY}s...")
            time.sleep(_RETRY_DELAY)
    raise RuntimeError(f"SmartAPI login failed after {_MAX_RETRIES} attempts: {last_err}")
