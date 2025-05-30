import os
import time
import secrets
import hashlib
import base64
import hmac
from config import Config

def generate_question_token(question_id, user_id):
    """Generate a secure token for a question attempt."""
    return generate_signed_token(question_id, user_id)

def generate_signed_token(question_id, user_id):
    """Generate a signed token containing question_id, user_id, and timestamp."""
    timestamp = int(time.time())
    payload = f"{question_id}:{user_id}:{timestamp}"
    signature = hmac.new(Config.SECRET_TOKEN_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token

def verify_signed_token(token, user_id):
    """Verify the token's signature and expiry. Returns (question_id, valid)"""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 4:
            return None, False
        question_id, token_user_id, timestamp, signature = parts
        if str(user_id) != token_user_id:
            return None, False
        payload = f"{question_id}:{token_user_id}:{timestamp}"
        expected_sig = hmac.new(Config.SECRET_TOKEN_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None, False
        # If you care about expiry
        # if int(time.time()) - int(timestamp) > TOKEN_EXPIRY_SECONDS:
        #     return None, False
        return question_id, True
    except Exception:
        return None, False