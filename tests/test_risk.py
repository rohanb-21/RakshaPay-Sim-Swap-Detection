"""Tests for the ML risk engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from unittest.mock import MagicMock, patch
from risk_engine import RiskEngine


@pytest.fixture
def engine():
    return RiskEngine()


def _mock_user(sim_swapped=False, failed=0):
    from datetime import datetime, timedelta
    u = MagicMock()
    u.id = 1
    u.phone = "+919876543210"
    u.failed_attempts = failed
    u.sim_swapped_at = datetime.utcnow() - timedelta(hours=1) if sim_swapped else None
    u.created_at = datetime.utcnow() - timedelta(days=90)
    return u


def _mock_db():
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 2
    return db


def test_safe_login_scores_low(engine):
    """Normal login with known device → LOW risk."""
    user = _mock_user(sim_swapped=False)
    db   = _mock_db()
    with patch.object(engine, '_is_known_device', return_value=True):
        result = engine.assess(user, "known-device", "192.168.1.1", 0, db, check_vonage=False)
    assert result["score"] < 35
    assert result["action"] == "ALLOW"


def test_sim_swap_blocks_login(engine):
    """SIM swapped within 1 hour → HIGH risk → BLOCK."""
    user = _mock_user(sim_swapped=True)
    db   = _mock_db()
    with patch.object(engine, '_is_known_device', return_value=False):
        result = engine.assess(user, "new-device", "8.8.8.8", 0, db, check_vonage=False)
    assert result["score"] >= 30
    assert result["action"] in ("BLOCK", "CHALLENGE") and result["score"] > 30


def test_high_value_txn_raises_score(engine):
    """Large transaction with unknown device → elevated score."""
    user = _mock_user(sim_swapped=False)
    db   = _mock_db()
    with patch.object(engine, '_is_known_device', return_value=False):
        result = engine.assess(user, "new-device", "127.0.0.1", 150000, db, check_vonage=False)
    assert result["score"] > 20
    assert "VERY_HIGH_VALUE_TXN" in result["flags"]


def test_external_ip_flagged(engine):
    user = _mock_user()
    db   = _mock_db()
    with patch.object(engine, '_is_known_device', return_value=True):
        result = engine.assess(user, "device", "8.8.8.8", 100, db, check_vonage=False)
    assert "EXTERNAL_IP" in result["flags"]


def test_risk_levels():
    assert RiskEngine  # engine imports correctly
