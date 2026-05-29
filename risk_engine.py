"""
RakshaPay — Hybrid Risk Engine
============================
Combines:
  1. Vonage real-time SIM swap signal
  2. XGBoost ML fraud probability
  3. Rule-based guards (account lockout, high-value txn)

Final risk score = weighted blend of ML score + rule overrides.
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

import joblib
import numpy as np

from vonage_client import vonage_client

logger = logging.getLogger("rakshapay.risk")

ML_DIR     = os.path.join(os.path.dirname(__file__), "ml")
MODEL_PATH  = os.path.join(ML_DIR, "fraud_model.pkl")
SCALER_PATH = os.path.join(ML_DIR, "scaler.pkl")
META_PATH   = os.path.join(ML_DIR, "model_meta.json")


class RiskEngine:
    def __init__(self):
        self.model  = joblib.load(MODEL_PATH)
        self.scaler = joblib.load(SCALER_PATH)
        with open(META_PATH) as f:
            self.meta = json.load(f)
        logger.info(f"✅ ML model loaded | AUC={self.meta['auc']} | F1={self.meta['f1']}")

    # ── Public API ────────────────────────────────────────────
    def assess(
        self,
        user,
        device_id: str,
        ip: str,
        amount: float,
        db,
        check_vonage: bool = True,
    ) -> dict:
        """
        Returns:
          score       0–100
          level       LOW | MEDIUM | HIGH
          action      ALLOW | CHALLENGE | BLOCK
          flags       list[str]
          ml_prob     float  (raw ML fraud probability)
          vonage_src  str
        """
        flags = []
        rule_score = 0

        # ── 1. Vonage SIM Swap check ──────────────────────────
        sim_result = vonage_client.check(user.phone, max_age_hours=72) if check_vonage else None
        vonage_swapped = sim_result.swapped if sim_result else False
        vonage_source  = sim_result.source  if sim_result else "skipped"

        # ── 2. Local DB SIM swap check (fallback / admin sim) ─
        db_swapped = False
        hours_since_swap = -1.0

        if user.sim_swapped_at:
            db_swapped = True
            hours_since_swap = (datetime.utcnow() - user.sim_swapped_at).total_seconds() / 3600

        sim_swapped = vonage_swapped or db_swapped

        if sim_swapped:
            if hours_since_swap < 1 or vonage_swapped:
                rule_score += 70
                flags.append("SIM_SWAP_CRITICAL")
            elif hours_since_swap < 24:
                rule_score += 55
                flags.append("SIM_SWAP_LAST_24H")
            else:
                rule_score += 30
                flags.append("SIM_SWAP_LAST_72H")

        # ── 3. Device check ───────────────────────────────────
        known_device = self._is_known_device(user.id, device_id, db)
        if not known_device:
            rule_score += 15
            flags.append("UNKNOWN_DEVICE")

        # ── 4. Transaction amount ─────────────────────────────
        if amount > 100000:
            rule_score += 20
            flags.append("VERY_HIGH_VALUE_TXN")
        elif amount > 50000:
            rule_score += 10
            flags.append("HIGH_VALUE_TXN")

        # ── 5. External IP ────────────────────────────────────
        ext_ip = self._is_external_ip(ip)
        if ext_ip:
            rule_score += 8
            flags.append("EXTERNAL_IP")

        # ── 6. Failed attempts ────────────────────────────────
        failed = user.failed_attempts or 0
        if failed >= 3:
            rule_score += 10
            flags.append(f"FAILED_ATTEMPTS_{failed}")

        # ── 7. ML Score ───────────────────────────────────────
        ml_prob = self._ml_score(
            hours_since_sim_swap=max(hours_since_swap, 0) if sim_swapped else -1,
            is_known_device=int(known_device),
            transaction_amount=amount,
            is_external_ip=int(ext_ip),
            login_hour=datetime.utcnow().hour,
            failed_attempts_1h=failed,
            account_age_days=self._account_age(user),
            txns_last_24h=self._txns_last_24h(user.id, db),
        )

        # Blend: 60% rules + 40% ML
        ml_score    = ml_prob * 100
        final_score = int(min(0.60 * rule_score + 0.40 * ml_score, 100))

        # Hard override: SIM_SWAP_CRITICAL always blocks
        if "SIM_SWAP_CRITICAL" in flags:
            final_score = max(final_score, 80)

        if final_score >= 70:
            level, action = "HIGH",   "BLOCK"
        elif final_score >= 35:
            level, action = "MEDIUM", "CHALLENGE"
        else:
            level, action = "LOW",    "ALLOW"

        return {
            "score":      final_score,
            "level":      level,
            "action":     action,
            "flags":      flags,
            "ml_prob":    round(ml_prob, 4),
            "vonage_src": vonage_source,
        }

    # ── Helpers ───────────────────────────────────────────────
    def _ml_score(self, **kwargs) -> float:
        features = [
            "hours_since_sim_swap", "is_known_device", "transaction_amount",
            "is_external_ip", "login_hour", "failed_attempts_1h",
            "account_age_days", "txns_last_24h",
        ]
        import pandas as pd
        X = pd.DataFrame([[kwargs[f] for f in features]], columns=features)
        X_s = self.scaler.transform(X)
        return float(self.model.predict_proba(X_s)[0][1])

    def _is_known_device(self, uid: int, device_id: str, db) -> bool:
        from models import KnownDevice
        row = db.query(KnownDevice).filter_by(user_id=uid, device_id=device_id).first()
        if not row:
            db.add(KnownDevice(user_id=uid, device_id=device_id))
            db.commit()
            return False
        return True

    def _is_external_ip(self, ip: str) -> bool:
        local = ("127.0.0.1", "localhost", "::1")
        return ip not in local and not ip.startswith(("10.", "192.168.", "172."))

    def _account_age(self, user) -> int:
        return max((datetime.utcnow() - user.created_at).days, 1)

    def _txns_last_24h(self, uid: int, db) -> int:
        from models import Transaction
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(hours=24)
        return db.query(Transaction).filter(
            Transaction.user_id == uid,
            Transaction.created_at >= since
        ).count()


# Singleton loaded once at startup
risk_engine = RiskEngine()
