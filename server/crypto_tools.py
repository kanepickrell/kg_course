"""
crypto_tools.py
===============
Tool class for the Crypto Helper agent.

Upload this file via the ATLAS App Onboarding Code step.
The agent will call these methods directly — no subprocess, stdlib only.

Methods:
    hash_string(text, algorithm)  — sha256 / md5 / sha1 / sha512
    base64_encode(text)           — standard base64 encode
    base64_decode(text)           — standard base64 decode
    generate_password(length)     — cryptographically random password
"""

import hashlib
import base64
import secrets
import string


class CryptoTools:

    # ── Hashing ───────────────────────────────────────────────────────────────

    def hash_string(self, text: str, algorithm: str = "sha256") -> dict:
        """
        Hash a string using the specified algorithm.
        Supported: sha256, sha512, sha1, md5.
        """
        algo = algorithm.lower().replace("-", "")
        supported = {"sha256", "sha512", "sha1", "md5"}

        if algo not in supported:
            return {
                "success": False,
                "error": f"Unsupported algorithm '{algorithm}'. Choose from: {', '.join(sorted(supported))}",
            }

        try:
            h = hashlib.new(algo, text.encode("utf-8"))
            digest = h.hexdigest()
            return {
                "success":   True,
                "input":     text,
                "algorithm": algo,
                "hash":      digest,
                "length":    len(digest),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Base64 ────────────────────────────────────────────────────────────────

    def base64_encode(self, text: str) -> dict:
        """Encode a plain-text string to standard base64."""
        try:
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            return {
                "success":  True,
                "input":    text,
                "encoded":  encoded,
                "length":   len(encoded),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def base64_decode(self, text: str) -> dict:
        """Decode a base64 string back to plain text."""
        try:
            # Add padding if needed
            padded = text + "=" * (-len(text) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
            return {
                "success": True,
                "input":   text,
                "decoded": decoded,
            }
        except Exception as e:
            return {"success": False, "error": f"Invalid base64: {e}"}

    # ── Password generation ───────────────────────────────────────────────────

    def generate_password(self, length: int = 16) -> dict:
        """
        Generate a cryptographically secure random password.
        Uses uppercase, lowercase, digits, and symbols.
        Min length 8, max 128.
        """
        length = max(8, min(int(length), 128))

        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        # Guarantee at least one of each character class
        password = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*()-_=+"),
        ]
        password += [secrets.choice(alphabet) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(password)

        pwd = "".join(password)
        return {
            "success":  True,
            "password": pwd,
            "length":   len(pwd),
            "strength": "strong" if length >= 16 else "moderate",
        }