import hashlib, hmac
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from config import settings

# ── Password Hashing (HMAC-SHA256 — no external deps) ─────────
_SALT = (settings.JWT_SECRET + "_pw_salt").encode()

def hash_password(password: str) -> str:
    return hmac.new(_SALT, password.encode(), hashlib.sha256).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(plain), hashed)


# ── JWT ────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ── Account Lockout ───────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES     = 15

def is_account_locked(user) -> bool:
    if user.locked_until and datetime.utcnow() < user.locked_until:
        return True
    return False

def should_lock(user) -> bool:
    return (user.failed_attempts or 0) >= MAX_FAILED_ATTEMPTS

# Keep sub as string for jose compatibility
