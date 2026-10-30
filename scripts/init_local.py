"""Run the local SQLite service without changing an existing .env file.

Usage: python scripts/init_local.py [--host 127.0.0.1] [--port 8000]
"""
import argparse
import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


def main():
    parser = argparse.ArgumentParser(description="Start VOLNA with a local SQLite database")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    os.chdir(BASE_DIR)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("AUTO_CREATE_TABLES", "true")
    if not os.environ.get("CLAMSCAN_PATH"):
        portable_dir = BASE_DIR / "tools" / "clamav"
        scanner = next(portable_dir.rglob("clamscan.exe"), None) if portable_dir.is_dir() else None
        if scanner is not None:
            os.environ["CLAMSCAN_PATH"] = str(scanner.resolve())
            os.environ.setdefault("CLAMAV_DATABASE_DIR", str((portable_dir / "database").resolve()))
    from app.core.config import settings
    settings.encryption_key()
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
