"""Integration coverage against isolated SQLite and real FFmpeg processing.

The antivirus success response is replaced only inside individual tests; the
production implementation has no bypass and is separately tested fail-closed.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

# Set configuration before importing the application's singleton engine.
_workspace = tempfile.TemporaryDirectory(prefix="volna-tests-")
_root = Path(_workspace.name)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_root / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_root / "data")
os.environ["MEDIA_DIR"] = str(_root / "media")
os.environ["TRACK_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["ENVIRONMENT"] = "development"
os.environ["COOKIE_SECURE"] = "false"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["CLAMAV_HOST"] = ""
os.environ["CLAMSCAN_PATH"] = "volna-test-scanner-does-not-exist"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.errors import ApplicationError
from app.infrastructure.media.antivirus import AntivirusScanner
from app.infrastructure.media.cleanup import CleanupService
from app.infrastructure.media.dependencies import get_audio_processor, get_audio_storage
from app.infrastructure.media.storage import EncryptedAudioStorage
from app.infrastructure.media.transcoder import AudioTranscoder
from app.modules.auth import dependencies as auth
from app.core.config import settings
from app.core.database import Base, async_engine, async_session_marker
from app.main import app
from app.models import Favorite, FileDeletion, PlaylistTrack, Session, Track, User

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(monkeypatch):
    storage = tempfile.TemporaryDirectory(prefix="case-", dir=_root)
    monkeypatch.setattr(settings, "MEDIA_DIR", Path(storage.name) / "tracks")
    auth._attempts.clear()
    get_audio_processor().reset_status_cache()
    with TestClient(app) as browser:
        async def reset():
            async with async_engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
                await connection.run_sync(Base.metadata.create_all)

        browser.portal.call(reset)
        yield browser
    auth._attempts.clear()
    get_audio_processor().reset_status_cache()
    storage.cleanup()


@pytest.fixture(scope="session")
def mp3():
    executable = AudioTranscoder().resolve_ffmpeg()
    assert executable, "Install imageio-ffmpeg or FFmpeg to exercise real audio processing"
    return subprocess.run(
        [executable, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=1", "-f", "mp3", "pipe:1"],
        capture_output=True, check=True,
    ).stdout


@pytest.fixture
def clean_scanner(monkeypatch):
    scans = []

    async def scan(self, data):
        scans.append(bytes(data))

    monkeypatch.setattr(AntivirusScanner, "scan", scan)
    return scans


def register(client, username="listener"):
    response = client.post("/auth/register", json={"username": username, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def login(client, username="listener"):
    response = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def write(client, method, url, **kwargs):
    me = client.get("/auth/me")
    assert me.status_code == 200, me.text
    headers = {"X-CSRF-Token": me.json()["csrf_token"], **kwargs.pop("headers", {})}
    return client.request(method, url, headers=headers, **kwargs)


def upload(client, content, name="Night flight", artist="Signal"):
    return write(client, "POST", "/api/tracks", data={"name": name, "artist": artist},
                 files={"file": ("tone.mp3", content, "audio/mpeg")})


def scalar(client, statement):
    async def run():
        async with async_session_marker() as db:
            return await db.scalar(statement)

    return client.portal.call(run)


def test_registration_login_normalization_and_revocation(client):
    me = register(client, "Listener")
    assert me["username"] == "listener"
    assert client.get("/auth/me").json() == me
    cookie = client.cookies.get(auth.COOKIE_NAME)
    assert cookie
    session_hash = hashlib.sha256(cookie.encode()).hexdigest()
    assert scalar(client, select(Session.token)) == session_hash
    stored_password = scalar(client, select(User.password_hash))
    assert PASSWORD not in stored_password and len(stored_password) > 64
    duplicate = client.post("/auth/register", json={"username": "LISTENER", "password": PASSWORD})
    assert duplicate.status_code == 409
    wrong = client.post("/auth/login", json={"username": "listener", "password": "wrong password here"})
    assert wrong.status_code == 401
    login(client, "LISTENER")
    assert client.cookies.get(auth.COOKIE_NAME) != cookie
    assert scalar(client, select(Session).where(Session.token == session_hash)) is None
    revoked_cookie = client.cookies.get(auth.COOKIE_NAME)
    assert write(client, "POST", "/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401
    client.cookies.set(auth.COOKIE_NAME, revoked_cookie)
    assert client.get("/auth/me").status_code == 401


def test_auth_cookie_csrf_origin_and_expiration(client):
    response = client.post("/auth/register", json={"username": "listener", "password": PASSWORD})
    assert response.status_code == 201
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header and "samesite=lax" in cookie_header
    assert "max-age=43200" in cookie_header
    assert client.post("/api/playlists", json={"name": "Private"}).status_code == 403
    assert client.post("/api/playlists", json={"name": "Private"}, headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert write(client, "POST", "/api/playlists", json={"name": "Private"}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/auth/login", json={"username": "listener", "password": PASSWORD}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403

    async def expire():
        async with async_session_marker() as db:
            session = await db.scalar(select(Session))
            session.expires = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()

    client.portal.call(expire)
    assert client.get("/auth/me").status_code == 401
    assert client.post("/api/playlists", json={"name": "Private"}).status_code == 401


def test_credential_validation_and_login_throttling(client):
    assert client.post("/auth/register", json={"username": "../bad", "password": PASSWORD}).status_code == 422
    assert client.post("/auth/register", json={"username": "listener", "password": "short"}).status_code == 422
    auth._attempts.clear()
    for _ in range(10):
        assert client.post("/auth/login", json={"username": "missing", "password": PASSWORD}).status_code == 401
    limited = client.post("/auth/login", json={"username": "missing", "password": PASSWORD})
    assert limited.status_code == 429 and limited.headers["retry-after"] == "60"


def test_anonymous_access_and_forged_upload(client, clean_scanner):
    assert client.get("/api/tracks").json()["total"] == 0
    assert client.get("/api/tracks?mine=true").status_code == 401
    assert client.get("/api/tracks?favorites=true").status_code == 401
    assert client.get("/api/playlists").status_code == 401
    denied = client.post("/api/tracks", data={"name": "Fake", "artist": "Fake"}, files={"file": ("fake.mp3", b"MZ malware", "audio/mpeg")})
    assert denied.status_code == 401
    register(client)
    assert upload(client, b"not an MP3").status_code == 400
    assert len(clean_scanner) == 1  # Original checked before the parser rejects it.
    assert client.get("/api/tracks").json()["total"] == 0
    assert not list(settings.media_dir.glob("*.enc"))


def test_real_audio_encryption_stream_ranges_search_and_owner(client, mp3, clean_scanner):
    owner = register(client)
    created = upload(client, mp3)
    assert created.status_code == 201, created.text
    track = created.json()
    assert track["owner_id"] == owner["id"]
    assert track["duration"] > .9 and track["file_size"] > 0
    assert "file_path" not in track and "file_name" not in track
    assert len(clean_scanner) == 2
    path = Path(scalar(client, select(Track.file_path)))
    encrypted = path.read_bytes()
    assert path.suffix == ".enc" and encrypted != mp3
    decoded = Fernet(settings.encryption_key()).decrypt(encrypted)
    stream = f"/api/tracks/{track['id']}/stream"
    full = client.get(stream)
    assert full.status_code == 200 and full.content == decoded
    assert full.headers["content-type"] == "audio/mpeg"
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["x-content-type-options"] == "nosniff"
    head = client.head(stream)
    assert head.status_code == 200 and head.content == b""
    assert int(head.headers["content-length"]) == len(decoded)
    segment = client.get(stream, headers={"Range": "bytes=10-29"})
    assert segment.status_code == 206 and segment.content == decoded[10:30]
    assert segment.headers["content-range"] == f"bytes 10-29/{len(decoded)}"
    suffix = client.get(stream, headers={"Range": "bytes=-15"})
    assert suffix.status_code == 206 and suffix.content == decoded[-15:]
    open_range = client.get(stream, headers={"Range": "bytes=10-"})
    assert open_range.status_code == 206 and open_range.content == decoded[10:]
    for value in ["bytes=-0", "bytes=999999999-", "bytes=20-10", "bytes=0-1,3-4", "garbage"]:
        invalid = client.get(stream, headers={"Range": value})
        assert invalid.status_code == 416 and invalid.headers["content-range"] == f"bytes */{len(decoded)}"
    assert client.get("/api/tracks?search=signal").json()["total"] == 1
    assert client.get("/api/tracks?search=%25").json()["total"] == 0
    assert client.get("/api/tracks?mine=true").json()["total"] == 1
    assert client.get("/api/tracks?page_size=101").status_code == 422
    register(client, "another")
    assert client.get("/api/tracks?mine=true").json()["total"] == 0
    assert write(client, "PATCH", f"/api/tracks/{track['id']}", json={"name": "Stolen", "artist": "Stolen"}).status_code == 403
    assert write(client, "DELETE", f"/api/tracks/{track['id']}").status_code == 403
    login(client)
    renamed = write(client, "PATCH", f"/api/tracks/{track['id']}", json={"name": " New name ", "artist": " Signal "})
    assert renamed.status_code == 200 and renamed.json()["name"] == "New name"


def test_favorites_and_private_playlists_idempotence(client, mp3, clean_scanner):
    register(client)
    track = upload(client, mp3).json()
    tid = track["id"]
    for _ in range(2):
        assert write(client, "PUT", f"/api/tracks/{tid}/favorite").status_code == 204
    assert scalar(client, select(func.count()).select_from(Favorite)) == 1
    favorites = client.get("/api/tracks?favorites=true").json()
    assert favorites["total"] == 1 and favorites["tracks"][0]["is_favorite"]
    created = write(client, "POST", "/api/playlists", json={"name": " Evening "})
    assert created.status_code == 201
    pid = created.json()["id"]
    for _ in range(2):
        assert write(client, "PUT", f"/api/playlists/{pid}/tracks/{tid}").status_code == 204
    assert scalar(client, select(func.count()).select_from(PlaylistTrack)) == 1
    assert client.get("/api/playlists").json()[0]["track_count"] == 1
    assert client.get(f"/api/playlists/{pid}/tracks").json()["tracks"][0]["id"] == tid
    register(client, "outsider")
    assert client.get("/api/playlists").json() == []
    assert client.get(f"/api/playlists/{pid}/tracks").status_code == 404
    assert write(client, "PATCH", f"/api/playlists/{pid}", json={"name": "Stolen"}).status_code == 404
    assert write(client, "DELETE", f"/api/playlists/{pid}").status_code == 404
    assert write(client, "PUT", f"/api/playlists/{pid}/tracks/{tid}").status_code == 404
    assert client.get("/api/tracks?favorites=true").json()["total"] == 0
    login(client)
    assert write(client, "PATCH", f"/api/playlists/{pid}", json={"name": "Renamed"}).status_code == 200
    for _ in range(2):
        assert write(client, "DELETE", f"/api/playlists/{pid}/tracks/{tid}").status_code == 204
        assert write(client, "DELETE", f"/api/tracks/{tid}/favorite").status_code == 204
    assert client.get(f"/api/playlists/{pid}/tracks").json()["total"] == 0
    assert client.get("/api/tracks?favorites=true").json()["total"] == 0
    assert write(client, "DELETE", f"/api/playlists/{pid}").status_code == 204
    assert client.get("/api/playlists").json() == []


@pytest.mark.parametrize("scanner_status", [400, 503])
def test_scanner_rejection_leaves_no_track_or_ciphertext(client, mp3, monkeypatch, scanner_status):
    async def failed(self, data):
        raise ApplicationError("Test scanner rejection", scanner_status)

    monkeypatch.setattr(AntivirusScanner, "scan", failed)
    register(client)
    failed_upload = upload(client, mp3)
    assert failed_upload.status_code == scanner_status
    assert scalar(client, select(func.count()).select_from(Track)) == 0
    assert list(settings.media_dir.iterdir()) == []


def test_track_delete_removes_file_and_collection_references(client, mp3, clean_scanner):
    register(client)
    tid = upload(client, mp3).json()["id"]
    path = Path(scalar(client, select(Track.file_path)))
    pid = write(client, "POST", "/api/playlists", json={"name": "Collection"}).json()["id"]
    write(client, "PUT", f"/api/playlists/{pid}/tracks/{tid}")
    write(client, "PUT", f"/api/tracks/{tid}/favorite")
    assert write(client, "DELETE", f"/api/tracks/{tid}").status_code == 204
    assert not path.exists()
    assert scalar(client, select(func.count()).select_from(Track)) == 0
    assert scalar(client, select(func.count()).select_from(Favorite)) == 0
    assert scalar(client, select(func.count()).select_from(PlaylistTrack)) == 0
    assert client.get(f"/api/tracks/{tid}/stream").status_code == 404
    assert client.get("/api/playlists").json()[0]["track_count"] == 0


def test_upload_status_fails_closed_when_scanner_is_absent(client):
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["uploads_ready"] is False
    assert status.json()["upload_message"]
    assert status.json()["max_upload_mb"] == settings.MAX_UPLOAD_MB


def test_sanitized_output_is_scanned_and_rejection_is_atomic(client, mp3, monkeypatch):
    calls = []

    async def reject_output(self, data):
        calls.append(data)
        if len(calls) == 2:
            raise ApplicationError("Test sanitized output rejection", 400)

    monkeypatch.setattr(AntivirusScanner, "scan", reject_output)
    register(client)
    assert upload(client, mp3).status_code == 400
    assert len(calls) == 2
    assert scalar(client, select(func.count()).select_from(Track)) == 0
    assert list(settings.media_dir.iterdir()) == []


def test_upload_file_limit_and_unsafe_filename(client, monkeypatch, clean_scanner):
    register(client)
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    assert upload(client, b"x" * (1024 * 1024 + 1)).status_code == 413
    assert clean_scanner == []
    assert scalar(client, select(func.count()).select_from(Track)) == 0
    for filename in ("../outside.mp3", "script.exe", "unsafe:name.mp3"):
        denied = write(client, "POST", "/api/tracks", data={"name": "Unsafe", "artist": "Unsafe"},
                       files={"file": (filename, b"test", "audio/mpeg")})
        assert denied.status_code == 400
    assert clean_scanner == []


def test_ciphertext_tampering_is_not_served(client, mp3, clean_scanner):
    register(client)
    tid = upload(client, mp3).json()["id"]
    path = Path(scalar(client, select(Track.file_path)))
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(data)
    response = client.get(f"/api/tracks/{tid}/stream")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")


def test_request_body_limits_declared_and_chunked(client):
    maximum = (settings.MAX_UPLOAD_MB + 1) * 1024 * 1024
    assert client.post("/api/tracks", content=b"tiny", headers={"Content-Length": str(maximum + 1)}).status_code == 413
    assert client.post("/auth/login", content=b"tiny", headers={"Content-Length": str(64 * 1024 + 1)}).status_code == 413
    assert client.post("/auth/login", content=b"tiny", headers={"Content-Length": "invalid"}).status_code == 400
    assert client.post("/auth/login", content=b"tiny", headers={"Content-Length": "-1"}).status_code == 413

    def chunks():
        for _ in range(65):
            yield b"x" * 1024

    chunked = client.post("/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert chunked.status_code == 413


def test_health_security_headers_and_missing_tracks(client):
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert client.get("/api/tracks/999/stream").status_code == 404
    assert client.get("/api/tracks").headers["cache-control"] == "no-store"


def test_deletion_survives_temporary_storage_failure(client, mp3, clean_scanner, monkeypatch):
    register(client)
    tid = upload(client, mp3).json()["id"]
    path = Path(scalar(client, select(Track.file_path)))
    real_remove = EncryptedAudioStorage.remove

    async def disk_busy(self, path):
        raise OSError("temporary test storage failure")

    monkeypatch.setattr(EncryptedAudioStorage, "remove", disk_busy)
    assert write(client, "DELETE", f"/api/tracks/{tid}").status_code == 204
    assert client.get("/api/tracks").json()["total"] == 0
    assert path.exists()
    assert scalar(client, select(func.count()).select_from(FileDeletion)) == 1
    monkeypatch.setattr(EncryptedAudioStorage, "remove", real_remove)

    async def retry():
        async with async_session_marker() as db:
            await CleanupService(db, get_audio_storage()).cleanup_files()

    client.portal.call(retry)
    assert not path.exists()
    assert scalar(client, select(func.count()).select_from(FileDeletion)) == 0


def test_quota_and_extreme_range_are_rejected(client, mp3, clean_scanner, monkeypatch):
    register(client)
    tid = upload(client, mp3).json()["id"]
    extreme = client.get(f"/api/tracks/{tid}/stream", headers={"Range": "bytes=" + "9" * 5000 + "-"})
    assert extreme.status_code == 416
    monkeypatch.setattr(settings, "MAX_USER_STORAGE_MB", 0)
    assert upload(client, mp3).status_code == 413
    assert scalar(client, select(func.count()).select_from(Track)) == 1
    invalid_origin = client.post("/auth/login", json={"username": "listener", "password": PASSWORD}, headers={"Origin": "http://["})
    assert invalid_origin.status_code == 403
