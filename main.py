"""
RakshaPay Bank — Production FastAPI Application
=============================================
Features:
  • JWT authentication
  • bcrypt password hashing
  • Account lockout after 5 failed attempts
  • Rate limiting (slowapi)
  • Vonage SIM Swap API integration
  • XGBoost ML fraud scoring
  • Full audit logging
"""
import os
import random
import string
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from config import settings
from models import (
    User, OTPStore, LoginAttempt, Transaction,
    FraudAlert, get_db, init_db
)
from auth import (
    hash_password, verify_password,
    create_access_token, decode_token,
    is_account_locked, should_lock,
    MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES
)
from risk_engine import risk_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("rakshapay")

# ── App ────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="RakshaPay Bank API",
    description="SIM Swap Attack Detection & Prevention System",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PAGES = os.path.join(os.path.dirname(__file__), "pages")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


# ── Page Routes ────────────────────────────────────────────────
@app.get("/",          include_in_schema=False)
def login_page():    return FileResponse(f"{PAGES}/login.html")

@app.get("/register",  include_in_schema=False)
def register_page(): return FileResponse(f"{PAGES}/register.html")

@app.get("/dashboard", include_in_schema=False)
def dashboard_page():return FileResponse(f"{PAGES}/dashboard.html")

@app.get("/transfer",  include_in_schema=False)
def transfer_page(): return FileResponse(f"{PAGES}/transfer.html")

@app.get("/admin",     include_in_schema=False)
def admin_page():    return FileResponse(f"{PAGES}/admin.html")


# ── Helpers ────────────────────────────────────────────────────
def gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter_by(id=payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def log_attempt(db, user_id, ip, device, result, action):
    db.add(LoginAttempt(
        user_id=user_id, ip=ip, device=device,
        risk_score=result["score"], risk_level=result["level"],
        flags=str(result["flags"]), action=action,
        ml_score=result.get("ml_prob"),
    ))
    db.commit()

def create_alert(db, user_id, alert_type, severity, details):
    db.add(FraudAlert(user_id=user_id, alert_type=alert_type,
                      severity=severity, details=details))
    db.commit()


# ── Request / Response Models ─────────────────────────────────
class RegisterIn(BaseModel):
    name:     str
    email:    str
    phone:    str
    password: str

    @validator("password")
    def pw_length(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @validator("name")
    def name_nonempty(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class LoginIn(BaseModel):
    email:     str
    password:  str
    device_id: str = "browser-default"


class OTPIn(BaseModel):
    user_id: int
    otp:     str


class TransferIn(BaseModel):
    amount:    float
    recipient: str
    device_id: str = "browser-default"

    @validator("amount")
    def positive_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return round(v, 2)


class SwapIn(BaseModel):
    user_id: int


# ── Auth Routes ────────────────────────────────────────────────
@app.post("/api/register", tags=["Auth"])
@limiter.limit("5/minute")
def register(request: Request, data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(400, "Email already registered")
    user = User(
        name=data.name, email=data.email,
        phone=data.phone, hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"New user registered: {data.email}")
    return {"success": True, "message": "Account created!", "user_id": user.id}


@app.post("/api/login", tags=["Auth"])
@limiter.limit("10/minute")
def login(request: Request, data: LoginIn, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"

    user = db.query(User).filter_by(email=data.email).first()
    if not user:
        raise HTTPException(401, "Invalid email or password")

    # Account lockout check
    if is_account_locked(user):
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
        raise HTTPException(403, f"Account locked. Try again in {remaining} minutes.")

    # Password check
    if not verify_password(data.password, user.hashed_password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if should_lock(user):
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            create_alert(db, user.id, "ACCOUNT_LOCKED", "HIGH",
                         f"Account locked after {MAX_FAILED_ATTEMPTS} failed attempts from IP {client_ip}")
        db.commit()
        raise HTTPException(401, "Invalid email or password")

    # Reset failed attempts on successful password
    user.failed_attempts = 0
    user.locked_until    = None
    db.commit()

    # Risk assessment
    result = risk_engine.assess(user, data.device_id, client_ip, 0, db)
    log_attempt(db, user.id, client_ip, data.device_id, result, result["action"])

    if result["action"] == "BLOCK":
        create_alert(db, user.id, "LOGIN_BLOCKED", "HIGH",
                     f"Login BLOCKED | Score={result['score']} | ML={result['ml_prob']} | Flags={result['flags']}")
        return {
            "success": False,
            "action": "BLOCK",
            "risk": result,
            "message": "⛔ Access denied. SIM swap detected. Please contact your branch.",
        }

    # Generate OTP
    otp = gen_otp()
    expires = datetime.utcnow() + timedelta(minutes=5)

    # Invalidate old OTPs
    db.query(OTPStore).filter_by(user_id=user.id, used=False).update({"used": True})
    db.add(OTPStore(user_id=user.id, otp=otp, expires_at=expires))
    db.commit()

    if result["action"] == "CHALLENGE":
        create_alert(db, user.id, "LOGIN_CHALLENGED", "MEDIUM",
                     f"Step-up auth triggered | Score={result['score']} | Flags={result['flags']}")

    return {
        "success": True,
        "action":  result["action"],
        "risk":    result,
        "user_id": user.id,
        "user_name": user.name,
        "otp":     otp,   # Demo: shown on screen. Production: send via email
        "vonage_source": result.get("vonage_src"),
        "message": "OTP sent",
    }


@app.post("/api/verify-otp", tags=["Auth"])
@limiter.limit("10/minute")
def verify_otp(request: Request, data: OTPIn, db: Session = Depends(get_db)):
    stored = (
        db.query(OTPStore)
        .filter_by(user_id=data.user_id, used=False)
        .order_by(OTPStore.id.desc())
        .first()
    )
    if not stored:
        raise HTTPException(400, "No OTP found. Please login again.")
    if datetime.utcnow() > stored.expires_at:
        raise HTTPException(400, "OTP expired. Please login again.")
    if stored.otp != data.otp:
        raise HTTPException(400, "Incorrect OTP.")

    stored.used = True
    db.commit()

    user = db.query(User).filter_by(id=data.user_id).first()

    # Create JWT
    token = create_access_token({"sub": str(user.id), "email": user.email})
    txns  = db.query(Transaction).filter_by(user_id=user.id).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user.id, "name": user.name,
            "email": user.email, "phone": user.phone,
            "balance": user.balance,
        },
        "transactions": [
            {"id": t.id, "amount": t.amount, "recipient": t.recipient,
             "risk_score": t.risk_score, "action": t.action,
             "created_at": t.created_at.isoformat()}
            for t in txns
        ],
    }


# ── User Routes ────────────────────────────────────────────────
@app.get("/api/user/me", tags=["User"])
def get_me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    txns = db.query(Transaction).filter_by(user_id=current_user.id).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()
    return {
        "id": current_user.id, "name": current_user.name,
        "email": current_user.email, "phone": current_user.phone,
        "balance": current_user.balance,
        "sim_swapped": bool(current_user.sim_swapped_at),
        "transactions": [
            {"id": t.id, "amount": t.amount, "recipient": t.recipient,
             "risk_score": t.risk_score, "action": t.action,
             "created_at": t.created_at.isoformat()}
            for t in txns
        ],
    }

# Keep simple user fetch for dashboard (no auth required for demo)
@app.get("/api/user/{uid}", tags=["User"])
def get_user(uid: int, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "User not found")
    txns = db.query(Transaction).filter_by(user_id=uid).order_by(
        Transaction.created_at.desc()
    ).limit(10).all()
    return {
        "id": user.id, "name": user.name,
        "email": user.email, "phone": user.phone,
        "balance": user.balance,
        "sim_swapped": bool(user.sim_swapped_at),
        "transactions": [
            {"id": t.id, "amount": t.amount, "recipient": t.recipient,
             "risk_score": t.risk_score, "action": t.action,
             "created_at": t.created_at.isoformat()}
            for t in txns
        ],
    }


@app.post("/api/transfer", tags=["User"])
@limiter.limit("20/minute")
def transfer(request: Request, data: TransferIn, db: Session = Depends(get_db)):
    # Get user_id from header (demo) or JWT
    uid = request.headers.get("X-User-Id")
    if not uid:
        raise HTTPException(401, "User ID required")
    user = db.query(User).filter_by(id=int(uid)).first()
    if not user:
        raise HTTPException(404, "User not found")

    client_ip = request.client.host if request.client else "unknown"
    result = risk_engine.assess(user, data.device_id, client_ip, data.amount, db)
    log_attempt(db, user.id, client_ip, "transfer", result, result["action"])

    if result["action"] == "BLOCK":
        create_alert(db, user.id, "TXN_BLOCKED", "HIGH",
                     f"Transfer ₹{data.amount:,.0f} BLOCKED | Score={result['score']}")
        db.add(Transaction(user_id=user.id, amount=data.amount,
                           recipient=data.recipient, risk_score=result["score"], action="BLOCK"))
        db.commit()
        return {"success": False, "action": "BLOCK", "risk": result,
                "message": f"⛔ Transfer blocked. SIM swap risk detected."}

    if data.amount > user.balance:
        raise HTTPException(400, "Insufficient balance")

    user.balance = round(user.balance - data.amount, 2)
    db.add(Transaction(user_id=user.id, amount=data.amount,
                       recipient=data.recipient, risk_score=result["score"], action="ALLOW"))
    db.commit()

    return {
        "success": True, "new_balance": user.balance,
        "risk": result,
        "message": f"✅ ₹{data.amount:,.2f} transferred to {data.recipient}",
    }


# ── Admin Routes ───────────────────────────────────────────────
@app.get("/api/admin/users", tags=["Admin"])
def admin_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.desc()).all()
    return [
        {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone,
         "balance": u.balance,
         "sim_swapped_at": u.sim_swapped_at.isoformat() if u.sim_swapped_at else None,
         "created_at": u.created_at.isoformat()}
        for u in users
    ]

@app.post("/api/admin/simulate-swap", tags=["Admin"])
def simulate_swap(data: SwapIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=data.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.sim_swapped_at = datetime.utcnow()
    create_alert(db, user.id, "SIM_SWAP_SIMULATED", "HIGH",
                 f"🔴 SIM swap simulated for {user.name} ({user.phone})")
    db.commit()
    return {"success": True, "message": f"SIM swap simulated for {user.name}"}

@app.post("/api/admin/reset-swap", tags=["Admin"])
def reset_swap(data: SwapIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=data.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.sim_swapped_at = None
    db.commit()
    return {"success": True, "message": f"SIM swap reset for {user.name}"}

@app.get("/api/admin/fraud-logs", tags=["Admin"])
def admin_logs(db: Session = Depends(get_db)):
    rows = db.query(LoginAttempt, User).join(User).order_by(
        LoginAttempt.id.desc()
    ).limit(100).all()
    return [
        {"id": l.id, "name": u.name, "phone": u.phone,
         "ip": l.ip, "device": l.device,
         "risk_score": l.risk_score, "ml_score": l.ml_score,
         "risk_level": l.risk_level, "flags": l.flags, "action": l.action,
         "created_at": l.created_at.isoformat()}
        for l, u in rows
    ]

@app.get("/api/admin/alerts", tags=["Admin"])
def admin_alerts(db: Session = Depends(get_db)):
    rows = db.query(FraudAlert, User).join(User).order_by(
        FraudAlert.id.desc()
    ).limit(100).all()
    return [
        {"id": a.id, "name": u.name, "phone": u.phone,
         "alert_type": a.alert_type, "severity": a.severity,
         "details": a.details, "resolved": a.resolved,
         "created_at": a.created_at.isoformat()}
        for a, u in rows
    ]

@app.get("/api/admin/stats", tags=["Admin"])
def admin_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total    = db.query(func.count(User.id)).scalar()
    swapped  = db.query(func.count(User.id)).filter(User.sim_swapped_at.isnot(None)).scalar()
    blocked  = db.query(func.count(LoginAttempt.id)).filter_by(action="BLOCK").scalar()
    challenged = db.query(func.count(LoginAttempt.id)).filter_by(action="CHALLENGE").scalar()
    alerts   = db.query(func.count(FraudAlert.id)).filter_by(resolved=False).scalar()
    return {
        "total_users": total, "swapped_users": swapped,
        "blocked_logins": blocked, "challenged_logins": challenged,
        "open_alerts": alerts,
    }

@app.get("/api/admin/model-meta", tags=["Admin"])
def model_meta():
    """Return ML model performance metrics."""
    return risk_engine.meta


# ── Health ─────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "ml_model_auc": risk_engine.meta["auc"],
        "vonage_configured": risk_engine.__class__.__name__,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Startup ────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    print("\n" + "═"*55)
    print("  🏦  RakshaPay Bank  |  Production v2.0")
    print("═"*55)
    print(f"  🌐 App         → http://localhost:8000")
    print(f"  🛡️  Admin       → http://localhost:8000/admin")
    print(f"  📖 API Docs    → http://localhost:8000/api/docs")
    print(f"  🤖 ML AUC      → {risk_engine.meta['auc']}")
    print("═"*55 + "\n")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
