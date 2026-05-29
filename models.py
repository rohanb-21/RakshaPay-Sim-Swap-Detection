from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config import settings

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String(100), nullable=False)
    email          = Column(String(150), unique=True, index=True, nullable=False)
    phone          = Column(String(20), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    balance        = Column(Float, default=100000.0)
    sim_swapped_at = Column(DateTime, nullable=True)
    failed_attempts = Column(Integer, default=0)
    locked_until   = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)

    login_attempts = relationship("LoginAttempt", back_populates="user")
    transactions   = relationship("Transaction",  back_populates="user")
    fraud_alerts   = relationship("FraudAlert",   back_populates="user")
    devices        = relationship("KnownDevice",  back_populates="user")
    otps           = relationship("OTPStore",     back_populates="user")


class OTPStore(Base):
    __tablename__ = "otp_store"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    otp        = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="otps")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    ip         = Column(String(50))
    device     = Column(String(255))
    risk_score = Column(Float)
    risk_level = Column(String(10))
    flags      = Column(Text)
    action     = Column(String(20))
    ml_score   = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="login_attempts")


class Transaction(Base):
    __tablename__ = "transactions"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount     = Column(Float, nullable=False)
    recipient  = Column(String(100))
    risk_score = Column(Float)
    action     = Column(String(20), default="ALLOW")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    alert_type = Column(String(50))
    severity   = Column(String(10))
    details    = Column(Text)
    resolved   = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="fraud_alerts")


class KnownDevice(Base):
    __tablename__ = "known_devices"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id  = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="devices")


# ── Engine & Session ─────────────────────────────────────────
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialised")
