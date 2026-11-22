"""Re-encrypt all application-encrypted data under DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID.

usage: python scripts/rotate_encryption_key.py [--status]

Run from the API environment (same .env). Safe to re-run: values already under the active key
are skipped. Take a backup first and keep every old key in DOCUMENT_ENCRYPTION_KEYS until
`--status` shows nothing remains under it.
"""
import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
api_root = project_root / "services" / "api"
sys.path.insert(0, str(api_root if api_root.is_dir() else project_root))

from src.database import check_connection  # noqa: E402
from src.services import key_rotation  # noqa: E402


async def main() -> None:
    if not await check_connection():
        raise SystemExit("Database unavailable.")
    if "--status" in sys.argv:
        print(json.dumps(await key_rotation.status(), indent=2))
        return
    print("Re-encrypting with the active key...")
    print(json.dumps(await key_rotation.rotate(), indent=2))
    print("Remaining by key id:")
    print(json.dumps(await key_rotation.status(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
