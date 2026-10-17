"""Shared HTTP Basic credentials for temporary team demos."""

import base64
import binascii
import hashlib
import hmac


class TeamGate:
    """Keep only a credential digest; never return credentials to the browser."""

    def __init__(self, password):
        if len(password.strip()) < 12 or len(password) > 256 or any(c in password for c in "\r\n\x00"):
            raise ValueError("Use a shared password of 12-256 characters without line breaks.")
        self.digest = hashlib.sha256(("team:" + password).encode("utf-8")).digest()

    def allows(self, header):
        scheme, separator, token = header.partition(" ")
        if not separator or scheme.lower() != "basic":
            return False
        try:
            credentials = base64.b64decode(token, validate=True)
        except (ValueError, binascii.Error):
            return False
        return hmac.compare_digest(hashlib.sha256(credentials).digest(), self.digest)
