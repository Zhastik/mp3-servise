"""Download a project-local portable ClamAV; no system installation or service.

Run with Python 3.11+ on Windows x64. Download comes only from the official
ClamAV distribution endpoint. Signature downloads may be rate limited by its CDN.
"""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

BASE_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = (BASE_DIR / "tools" / "clamav").resolve()
ARCHIVE_URL = "https://www.clamav.net/downloads/production/clamav-1.4.6.win.x64.zip"
GITHUB_ARCHIVE_URL = "https://github.com/Cisco-Talos/clamav/releases/download/clamav-1.4.6/clamav-1.4.6.win.x64.zip"
ARCHIVE_SHA256 = "57b6fd1d60cd87bafe800f97407ecdef0576d36b3900b8b7abcfbbabe88295fd"
MAX_DOWNLOAD = 300 * 1024 * 1024
MAX_EXTRACTED = 900 * 1024 * 1024


def download_archive(destination: Path, url: str = ARCHIVE_URL) -> None:
    print("Downloading portable ClamAV from its official distribution server...", flush=True)
    if url not in (ARCHIVE_URL, GITHUB_ARCHIVE_URL):
        raise RuntimeError("Only the official ClamAV distribution endpoints are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "VOLNA-local-setup/1.0"})
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=45) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise RuntimeError("ClamAV archive exceeds the expected download size")
                output.write(chunk)
        print(f"Downloaded {total // (1024 * 1024)} MB.", flush=True)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def safe_extract(archive: Path) -> None:
    with archive.open("rb") as content:
        if hashlib.file_digest(content, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise RuntimeError("ClamAV release checksum does not match the official release")
    print("Extracting into this project's tools/clamav directory...", flush=True)
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if sum(member.file_size for member in members) > MAX_EXTRACTED:
            raise RuntimeError("Unexpectedly large ClamAV archive")
        for member in members:
            name = PurePosixPath(member.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or any(":" in part for part in name.parts):
                raise RuntimeError("Unsafe archive path rejected")
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise RuntimeError("Archive symlinks are not allowed")
            target = (TOOLS_DIR / Path(*name.parts)).resolve()
            if not target.is_relative_to(TOOLS_DIR):
                raise RuntimeError("Archive path escapes project tools directory")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as content, target.open("wb") as output:
                    shutil.copyfileobj(content, output, 1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", choices=(ARCHIVE_URL, GITHUB_ARCHIVE_URL), default=ARCHIVE_URL)
    args = parser.parse_args()
    if sys.platform != "win32":
        print("This helper is for Windows x64. Use Docker Compose on other platforms.")
        return 1
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    scanner = next(TOOLS_DIR.rglob("clamscan.exe"), None)
    if scanner is None:
        archive = TOOLS_DIR / "clamav-portable.zip"
        if not archive.exists():
            try:
                download_archive(archive, args.url)
            except urllib.error.HTTPError as exc:
                print(f"Official ClamAV download returned HTTP {exc.code}; no system changes made.")
                return 2
            except (OSError, urllib.error.URLError):
                print("Official ClamAV download could not complete; no system changes made.")
                return 2
        safe_extract(archive)
        scanner = next(TOOLS_DIR.rglob("clamscan.exe"), None)
        if scanner is None:
            raise RuntimeError("Portable archive did not contain clamscan.exe")
    updater = scanner.with_name("freshclam.exe")
    if not updater.is_file():
        raise RuntimeError("Portable archive did not contain freshclam.exe")
    database = TOOLS_DIR / "database"
    database.mkdir(parents=True, exist_ok=True)
    config = scanner.parent / "freshclam.conf"
    config.write_text(
        f'DatabaseDirectory "{database}"\n'
        'DatabaseMirror database.clamav.net\n'
        'DNSDatabaseInfo current.cvd.clamav.net\n'
        'ConnectTimeout 20\nReceiveTimeout 60\nMaxAttempts 2\n',
        encoding="utf-8",
    )
    # The local launcher passes this database directory explicitly to clamscan.
    print("Updating official antivirus signatures (up to 5 minutes)...", flush=True)
    log = TOOLS_DIR / "freshclam.log"
    try:
        with log.open("wb") as output:
            result = subprocess.run(
                [str(updater), f"--config-file={config}"],
                cwd=scanner.parent, stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT, timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except subprocess.TimeoutExpired:
        print("Signature update timed out. See tools/clamav/freshclam.log; uploads remain blocked.")
        return 3
    if result.returncode != 0:
        print(f"Signature update failed (exit {result.returncode}). See tools/clamav/freshclam.log; uploads remain blocked.")
        return 3
    print("Portable ClamAV and official signatures are ready. Restart the local service.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Portable antivirus setup failed: {type(exc).__name__}. No system installation was performed.")
        raise SystemExit(1)
