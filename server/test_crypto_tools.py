#!/usr/bin/env python3
"""
test_crypto_tools.py
====================
Run this before onboarding to confirm every method works correctly.

    python test_crypto_tools.py

All tests should print PASS. Any FAIL means fix crypto_tools.py first.
"""

import sys
import hashlib
import base64

sys.path.insert(0, ".")
from crypto_tools import CryptoTools

t = CryptoTools()
failures = 0


def check(label, result, expected_key, expected_value=None):
    global failures
    if not result.get("success"):
        print(f"  FAIL  {label} — error: {result.get('error')}")
        failures += 1
        return
    if expected_value is not None and result.get(expected_key) != expected_value:
        print(f"  FAIL  {label}")
        print(f"        expected {expected_key}={expected_value!r}")
        print(f"        got      {expected_key}={result.get(expected_key)!r}")
        failures += 1
        return
    print(f"  PASS  {label}  →  {result.get(expected_key, '')}")


print("\n── hash_string ──────────────────────────────────────────")

# Known sha256 of "hello"
expected_sha256 = hashlib.sha256(b"hello").hexdigest()
check("sha256 of 'hello'",        t.hash_string("hello", "sha256"),  "hash", expected_sha256)
check("sha256 default algorithm", t.hash_string("hello"),             "hash", expected_sha256)
check("md5 of 'hello'",           t.hash_string("hello", "md5"),      "hash", hashlib.md5(b"hello").hexdigest())
check("sha1 of 'hello'",          t.hash_string("hello", "sha1"),     "hash", hashlib.sha1(b"hello").hexdigest())
check("sha512 of 'hello'",        t.hash_string("hello", "sha512"),   "hash", hashlib.sha512(b"hello").hexdigest())

# Bad algorithm should fail gracefully
r = t.hash_string("hello", "rot13")
if not r.get("success") and "error" in r:
    print("  PASS  bad algorithm returns error gracefully")
else:
    print("  FAIL  bad algorithm should return success=False")
    failures += 1

print("\n── base64_encode / decode ───────────────────────────────")

expected_b64 = base64.b64encode(b"hello world").decode("ascii")
check("encode 'hello world'", t.base64_encode("hello world"), "encoded", expected_b64)
check("decode back",          t.base64_decode(expected_b64),  "decoded", "hello world")

# Round-trip test
sample = "318th RANS ATLAS system"
enc = t.base64_encode(sample)
dec = t.base64_decode(enc["encoded"])
if dec.get("decoded") == sample:
    print(f"  PASS  round-trip encode→decode  →  {sample!r}")
else:
    print(f"  FAIL  round-trip mismatch: got {dec.get('decoded')!r}")
    failures += 1

# Bad base64
r = t.base64_decode("not!!valid==base64$$")
if not r.get("success"):
    print("  PASS  invalid base64 returns error gracefully")
else:
    print("  FAIL  invalid base64 should return success=False")
    failures += 1

print("\n── generate_password ────────────────────────────────────")

r = t.generate_password(16)
check("length=16", r, "length", 16)
if r.get("strength") == "strong":
    print("  PASS  strength=strong for length 16")
else:
    print(f"  FAIL  expected strength=strong, got {r.get('strength')!r}")
    failures += 1

r8 = t.generate_password(8)
check("length=8",  r8, "length", 8)

# Min/max clamping
r_tiny = t.generate_password(2)
if r_tiny.get("length", 0) >= 8:
    print(f"  PASS  length clamped to min 8  →  got {r_tiny['length']}")
else:
    print(f"  FAIL  length should clamp to 8, got {r_tiny.get('length')}")
    failures += 1

r_huge = t.generate_password(999)
if r_huge.get("length", 0) <= 128:
    print(f"  PASS  length clamped to max 128  →  got {r_huge['length']}")
else:
    print(f"  FAIL  length should clamp to 128, got {r_huge.get('length')}")
    failures += 1

# Two passwords should not be equal (probabilistically certain)
p1 = t.generate_password(24)["password"]
p2 = t.generate_password(24)["password"]
if p1 != p2:
    print("  PASS  two generated passwords are unique")
else:
    print("  FAIL  two passwords were identical (extremely unlikely — check secrets module)")
    failures += 1

print("\n─────────────────────────────────────────────────────────")
if failures == 0:
    print(f"  ALL TESTS PASSED — safe to onboard crypto_tools.py\n")
else:
    print(f"  {failures} TEST(S) FAILED — fix before onboarding\n")
    sys.exit(1)