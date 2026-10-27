import hashlib
import hmac
import secrets

_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_value: str) -> tuple[bool, bool]:
    """Return (valid, needs_rehash); legacy plaintext is accepted once for migration."""
    if not stored_value.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored_value), True

    try:
        _, iterations, salt_hex, digest_hex = stored_value.split("$", 3)
        iterations_value = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False, False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations_value)
    return hmac.compare_digest(actual, expected), iterations_value < _ITERATIONS