"""
RakshaPay — Vonage SIM Swap Client
================================
Uses the real Vonage Identity Insights API.
Falls back to sandbox mode when no credentials are configured,
so the project works out-of-the-box for demos.

Sandbox virtual numbers (+990...):
  max_age < 500  → swapped = False
  max_age >= 500 → swapped = True
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional

from config import settings

logger = logging.getLogger("rakshapay.vonage")


class SimSwapResult:
    def __init__(self, swapped: bool, last_swap: Optional[datetime], source: str):
        self.swapped   = swapped
        self.last_swap = last_swap
        self.source    = source   # "vonage_live" | "vonage_sandbox" | "local_db"

    def __repr__(self):
        return f"<SimSwapResult swapped={self.swapped} source={self.source}>"


class VonageSimSwapClient:
    """
    Wraps Vonage Network SIM Swap API.

    Usage:
        client = VonageSimSwapClient()
        result = client.check(phone_number="+919876543210", max_age_hours=72)
        if result.swapped:
            # block login
    """

    def __init__(self):
        self.configured = bool(
            settings.VONAGE_APPLICATION_ID and
            settings.VONAGE_APPLICATION_ID != "your-vonage-app-id" and
            os.path.exists(settings.VONAGE_PRIVATE_KEY_PATH)
        )
        self._client = None
        if self.configured:
            self._init_vonage()

    def _init_vonage(self):
        try:
            from vonage import Vonage, Auth
            auth = Auth(
                application_id=settings.VONAGE_APPLICATION_ID,
                private_key=settings.VONAGE_PRIVATE_KEY_PATH,
            )
            self._client = Vonage(auth)
            logger.info("✅ Vonage client initialised (live mode)")
        except Exception as e:
            logger.warning(f"Vonage init failed: {e} — falling back to sandbox")
            self.configured = False

    def check(self, phone_number: str, max_age_hours: int = 72) -> SimSwapResult:
        """
        Returns SimSwapResult.
        If Vonage is configured → real API call.
        Else → sandbox simulation using virtual +990 numbers.
        """
        if self.configured and self._client:
            return self._live_check(phone_number, max_age_hours)
        return self._sandbox_check(phone_number, max_age_hours)

    def _live_check(self, phone: str, max_age_hours: int) -> SimSwapResult:
        try:
            from vonage_network_sim_swap.requests import SimSwapCheckRequest
            response = self._client.network_sim_swap.check(
                SimSwapCheckRequest(phone_number=phone, max_age=max_age_hours)
            )
            swapped = response.get("swapped", False)
            logger.info(f"Vonage live check {phone}: swapped={swapped}")
            return SimSwapResult(swapped=swapped, last_swap=None, source="vonage_live")
        except Exception as e:
            logger.error(f"Vonage live check error: {e}")
            return SimSwapResult(swapped=False, last_swap=None, source="vonage_live_error")

    def _sandbox_check(self, phone: str, max_age_hours: int) -> SimSwapResult:
        """
        Vonage sandbox rules:
          +990 numbers → virtual operator
          max_age >= 500 → swapped = True
          max_age < 500  → swapped = False
        For non-+990 numbers we return False (no data available in sandbox).
        """
        is_virtual = phone.startswith("+990")
        if is_virtual:
            swapped = max_age_hours >= 500
        else:
            swapped = False   # sandbox can't check real numbers

        logger.info(f"Vonage sandbox check {phone}: swapped={swapped}")
        return SimSwapResult(swapped=swapped, last_swap=None, source="vonage_sandbox")


# Singleton
vonage_client = VonageSimSwapClient()
