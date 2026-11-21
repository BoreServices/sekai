"""Self-hosted ALTCHA proof-of-work captcha.

No third-party service is contacted. The server issues a random salt and a
number range, signed with an HMAC key that never leaves the process. The
browser widget brute-forces a counter whose SHA-256 hash (of salt + number)
starts with a hex prefix. The server re-derives the signature and hash, so a
solution is accepted only if it was issued by us, is still fresh, and has not
been used before.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict

ALGORITHM = "SHA-256"
MAX_NUMBER = 500_000  # ~0.5M attempts: a few seconds on a phone, costly for bots
KEY_PREFIX_LENGTH = 2  # 2 hex chars = 1/256 odds per try, ~128 tries average
EXPIRES_IN = 300  # seconds a challenge stays valid
SEEN_LIMIT = 10_000

_KEY = secrets.token_bytes(32)
_seen: OrderedDict[str, float] = OrderedDict()


def _sign(challenge: str, salt_expires: str) -> str:
    return hmac.new(_KEY, f"{challenge}|{salt_expires}".encode(), hashlib.sha256).hexdigest()


def create_challenge() -> dict:
    """Return a challenge the widget can solve, signed by this server."""
    expires = int(time.time()) + EXPIRES_IN
    salt = f"{secrets.token_hex(16)}?expires={expires}"
    number = secrets.randbelow(MAX_NUMBER)
    challenge = hashlib.sha256(f"{salt}{number}".encode()).hexdigest()[:KEY_PREFIX_LENGTH]
    # The prefix is the difficulty target; the number stays hidden in the hash.
    return {
        "algorithm": ALGORITHM,
        "challenge": challenge,
        "salt": salt,
        "signature": _sign(challenge, salt),
        "maxnumber": MAX_NUMBER,
    }


def _decode_payload(payload: str) -> dict | None:
    try:
        raw = base64.b64decode(payload, validate=True)
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def verify_solution(payload: str) -> bool:
    """Return True only for a fresh, server-issued, correctly solved, unused challenge."""
    if not payload or len(payload) > 4096:
        return False
    data = _decode_payload(payload)
    if data is None:
        return False

    algorithm = data.get("algorithm")
    challenge = data.get("challenge")
    salt = data.get("salt")
    signature = data.get("signature")
    number = data.get("number")
    if (
        algorithm != ALGORITHM
        or not isinstance(challenge, str)
        or not isinstance(salt, str)
        or not isinstance(signature, str)
        or not isinstance(number, int)
        or isinstance(number, bool)
        or not 0 <= number < MAX_NUMBER
    ):
        return False

    if not hmac.compare_digest(signature, _sign(challenge, salt)):
        return False

    _, _, query = salt.partition("?expires=")
    try:
        expires = int(query)
    except ValueError:
        return False
    if time.time() > expires:
        return False

    digest = hashlib.sha256(f"{salt}{number}".encode()).hexdigest()
    if not digest.startswith(challenge):
        return False

    # Single use: remember the signature until the challenge has expired.
    now = time.time()
    _prune(now)
    if signature in _seen:
        return False
    _seen[signature] = expires
    while len(_seen) > SEEN_LIMIT:
        _seen.popitem(last=False)
    return True


def _prune(now: float) -> None:
    stale = [key for key, expires in _seen.items() if expires < now]
    for key in stale:
        del _seen[key]
