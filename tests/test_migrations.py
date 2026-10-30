"""Exercise the actual upgrade path without connecting to the user's database."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def migrate(path, revision):
    environment = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path.as_posix()}"}
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=ROOT,
                            env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_existing_database_upgrades_and_untrusted_files_stay_private():
    with tempfile.TemporaryDirectory(prefix="volna-migration-") as directory:
        path = Path(directory) / "old.db"
        migrate(path, "f102_auth")
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("INSERT INTO users VALUES (1, 'legacy', 'preserved-hash')")
            connection.execute("INSERT INTO sessions VALUES ('old-session', 1, '2099-01-01')")
            connection.execute("INSERT INTO author VALUES (1, 'Artist', 1)")
            connection.execute("INSERT INTO track (id,name,is_active,author_id,owner_id,file_path) VALUES (1,'Old track',1,1,1,'media/old.mp3')")
            connection.execute("INSERT INTO playlist VALUES (1,'Old playlist',1)")
            connection.execute("INSERT INTO playlisttrackmodel VALUES (1,1,1)")
            connection.execute("INSERT INTO playlisttrackmodel VALUES (2,1,1)")
            connection.commit()
        migrate(path, "head")
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "f103_service"
            assert connection.execute("SELECT password_hash FROM users").fetchone()[0] == "preserved-hash"
            assert connection.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
            assert connection.execute("SELECT artist,is_active,file_path FROM track").fetchone() == ("Artist", 0, "media/old.mp3")
            assert connection.execute("SELECT count(*) FROM playlisttrackmodel").fetchone()[0] == 1
            assert connection.execute("SELECT count(*) FROM file_deletions").fetchone()[0] == 0
            connection.execute("INSERT INTO favorites (user_id,track_id) VALUES (1,1)")
