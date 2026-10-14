from datetime import time, timedelta, timezone
import os
try:
    from zoneinfo import ZoneInfo
    IST_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    IST_TZ = timezone(timedelta(hours=5, minutes=30))

TIMEZONE = "Asia/Kolkata"
CURFEW = time(22, 0)
GUEST_CUTOFF = time(20, 0)

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-dev-key-hostel-pass-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 12

DB_URL = os.getenv("DB_URL", "sqlite:///./hostel.db")

