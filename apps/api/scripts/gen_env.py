"""Create .env from .env.example with fresh secrets. Leaves an existing .env alone.

uv run python scripts/gen_env.py [--force]
"""

from __future__ import annotations

import base64
import re
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[3]


def vapid_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    raw_private = key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    return b64(raw_public), b64(raw_private)


def main() -> None:
    target = ROOT / ".env"
    if target.exists() and "--force" not in sys.argv:
        print(".env exists; leaving it alone (use --force to regenerate)")
        return
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    public, private = vapid_pair()
    values = {
        "JWT_SECRET": secrets.token_urlsafe(48),
        "DATA_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
        "DATA_HASH_KEY": secrets.token_urlsafe(32),
        "VAPID_PUBLIC_KEY": public,
        "VAPID_PRIVATE_KEY": private,
        "WHATSAPP_VERIFY_TOKEN": secrets.token_urlsafe(16),
    }
    for key, value in values.items():
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.MULTILINE)
    target.write_text(text, encoding="utf-8")
    print("wrote .env with fresh secrets")


if __name__ == "__main__":
    main()
