import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# SmartAPI credentials
API_KEY     = os.getenv("SMARTAPI_API_KEY", "")
CLIENT_ID   = os.getenv("SMARTAPI_CLIENT_ID", "")
PASSWORD    = os.getenv("SMARTAPI_PASSWORD", "")
TOTP_SECRET = os.getenv("SMARTAPI_TOTP_SECRET", "")

# Mode + risk
PAPER                = os.getenv("PAPER", "true").lower() == "true"
CAPITAL              = float(os.getenv("CAPITAL", "100000"))
MAX_RISK_PCT         = float(os.getenv("MAX_RISK_PCT", "1.0"))
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "2.0"))

# Instrument constants
MCX_EXCHANGE = "MCX"
FULL_NAME    = "CRUDEOIL"    # 100-bbl full contract — OI chain analysis
MINI_NAME    = "CRUDEOILM"   # 10-bbl mini contract  — execution instrument
FULL_LOT     = 100
MINI_LOT     = 10
STRIKE_STEP  = 100           # ₹100/bbl strike increments on MCX

# Analysis
ATM_WINGS = 5   # ATM ± n strikes shown in strip

# Scrip master cache
SCRIP_MASTER_URL  = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
SCRIP_CACHE_FILE  = Path(__file__).parent / ".scrip_master_cache.json"
SCRIP_CACHE_HOURS = 6

SESSION_CACHE_FILE = Path(__file__).parent / ".session_cache.json"

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
