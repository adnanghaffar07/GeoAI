"""Passwords and one-time tokens.

- Passwords are hashed with Argon2 (pwdlib). The password itself is never stored.
- Session cookies, invitation links, and reset links carry a long random token.
  The database stores only a SHA-256 hash of it, so a leaked copy of the database
  cannot be used to sign in or to use a link.
"""

import hashlib
import secrets

from pwdlib import PasswordHash

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

_password_hash = PasswordHash.recommended()
# Used when the email is unknown, so a failed sign-in takes the same time either way
# (prevents discovering which emails have accounts by measuring response time).
_DUMMY_HASH = _password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Return True if the password matches. Always does the same amount of work."""
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


def new_token() -> str:
    """A random, URL-safe token (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The form in which tokens are stored and looked up."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()
