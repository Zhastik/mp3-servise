"""Create private Compose secrets without replacing the existing project .env."""
from pathlib import Path
import os
import secrets
from cryptography.fernet import Fernet


def main():
    target = Path(__file__).resolve().parents[1] / ".env.docker"
    content = (
        "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32) + "\n"
        "TRACK_ENCRYPTION_KEY=" + Fernet.generate_key().decode() + "\n"
        "ENVIRONMENT=development\nCOOKIE_SECURE=false\nWEB_PORT=8080\n"
        "ALLOWED_HOSTS=localhost,127.0.0.1\n"
    )
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(".env.docker already exists; existing secrets retained.")
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)
    print("Created .env.docker. Keep this file private and back it up with your data.")


if __name__ == "__main__":
    main()
