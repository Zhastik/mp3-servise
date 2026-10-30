"""Password and token primitives, independent of the HTTP framework."""
import asyncio
import hashlib

from app.core.errors import ApplicationError

SCRYPT_N = 131072
_kdf_slots = asyncio.Semaphore(2)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password: str, salt: str, n: int = SCRYPT_N) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt), n=n, r=8, p=1,
        maxmem=256 * 1024 * 1024,
    ).hex()


async def derive_password(password: str, salt: str, n: int = SCRYPT_N) -> str:
    try:
        await asyncio.wait_for(_kdf_slots.acquire(), timeout=2)
    except TimeoutError:
        raise ApplicationError("Сервис входа занят. Повторите попытку позже.", 429, {"Retry-After": "3"})
    # Shielding keeps the slot occupied until the native computation ends even
    # when a client disconnects; cancelled calls cannot exceed the KDF budget.
    task = asyncio.create_task(asyncio.to_thread(password_hash, password, salt, n))
    try:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
    finally:
        _kdf_slots.release()


def encode_password(salt: str, hashed: str) -> str:
    return f"scrypt${SCRYPT_N}$8$1${salt}${hashed}"


def decode_password(stored: str) -> tuple[str, str, int]:
    if stored.startswith("scrypt$"):
        algorithm, n, r, p, salt, hashed = stored.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (SCRYPT_N, 8, 1):
            raise ValueError("Unsupported password hash")
        return salt, hashed, int(n)
    salt, hashed = stored.split(":")
    return salt, hashed, 16384
