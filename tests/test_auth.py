"""Tests for authentication utilities."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from auth import hash_password, verify_password, create_access_token, decode_token


def test_password_hashing():
    hashed = hash_password("mypassword123")
    assert hashed != "mypassword123"
    assert verify_password("mypassword123", hashed)

def test_wrong_password_fails():
    hashed = hash_password("correct_password")
    assert not verify_password("wrong_password", hashed)

def test_jwt_encode_decode():
    token = create_access_token({"sub": "42", "email": "test@test.com"})
    assert isinstance(token, str)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "test@test.com"

def test_invalid_token_returns_none():
    assert decode_token("totally.invalid.token") is None

def test_empty_token_returns_none():
    assert decode_token("") is None
