import logging

import pyotp
from SmartApi import SmartConnect

from config import API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET

# SmartAPI's internal logger is very noisy — suppress INFO/WARNING
logging.getLogger("SmartApi.smartConnect").setLevel(logging.CRITICAL)
logging.getLogger("SmartApi").setLevel(logging.CRITICAL)


def get_session() -> SmartConnect:
    """Always does a fresh login. SmartAPI invalidates prior tokens on new login,
    so cross-process session caching is unreliable."""
    obj = SmartConnect(api_key=API_KEY)
    totp_code = pyotp.TOTP(TOTP_SECRET).now()
    resp = obj.generateSession(CLIENT_ID, PASSWORD, totp_code)
    if not resp or not resp.get("status"):
        raise RuntimeError(f"SmartAPI login failed: {resp}")
    return obj
