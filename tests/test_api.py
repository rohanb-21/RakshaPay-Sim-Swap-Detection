"""Integration tests for the FastAPI endpoints."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use in-memory SQLite for tests
os.environ["DATABASE_URL"] = "sqlite:///./test_rakshapay.db"

from models import Base, get_db
from main import app

TEST_DB_URL = "sqlite:///./test_rakshapay.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

def override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_user():
    r = client.post("/api/register", json={
        "name": "Test User", "email": "test@test.com",
        "phone": "9999999999", "password": "password123"
    })
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_duplicate_email_rejected():
    payload = {"name": "A", "email": "dup@test.com", "phone": "111", "password": "pass123"}
    client.post("/api/register", json=payload)
    r = client.post("/api/register", json=payload)
    assert r.status_code == 400


def test_login_success():
    client.post("/api/register", json={
        "name": "Login Test", "email": "login@test.com",
        "phone": "8888888888", "password": "mypassword"
    })
    r = client.post("/api/login", json={
        "email": "login@test.com", "password": "mypassword"
    })
    data = r.json()
    assert r.status_code == 200
    assert data["success"] is True
    assert data["action"] in ("ALLOW", "CHALLENGE", "BLOCK")


def test_wrong_password_rejected():
    client.post("/api/register", json={
        "name": "A", "email": "a@test.com",
        "phone": "7777777777", "password": "correct"
    })
    r = client.post("/api/login", json={"email": "a@test.com", "password": "wrong"})
    assert r.status_code == 401


def test_short_password_rejected():
    r = client.post("/api/register", json={
        "name": "B", "email": "b@test.com", "phone": "6666", "password": "ab"
    })
    assert r.status_code == 422   # validation error


def test_admin_stats():
    r = client.get("/api/admin/stats")
    assert r.status_code == 200
    assert "total_users" in r.json()


def test_model_meta_endpoint():
    r = client.get("/api/admin/model-meta")
    assert r.status_code == 200
    assert "auc" in r.json()
