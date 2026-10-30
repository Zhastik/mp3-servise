"""Bootstrap signatures from the official preloaded clamav/clamav:1.4 image.

Use only when the regular FreshClam endpoint is unavailable. No container runtime
is needed; only the signature database layer is downloaded, verified by its OCI
SHA256 digest, and allowlisted database files are copied into project tools.
Continue using FreshClam for normal updates. Database signatures remain intact.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time
import urllib.error
import urllib.request

BASE_DIR = Path(__file__).resolve().parents[1]
ROOT = BASE_DIR / "tools" / "clamav"
REGISTRY = "https://registry-1.docker.io/v2/clamav/clamav"
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
))
ALLOWED_FILES = {
    f"var/lib/clamav/{name}.{extension}"
    for name in ("main", "daily", "bytecode") for extension in ("cvd", "cld")
}


def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=20) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise RuntimeError("Unexpected registry metadata size")
    return json.loads(data)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    auth = get_json("https://auth.docker.io/token?service=registry.docker.io&scope=repository:clamav/clamav:pull")
    # Anonymous, short-lived, read-only token stays in memory only.
    headers = {"Authorization": "Bearer " + auth["token"], "Accept": ACCEPT}
    manifest = get_json(REGISTRY + "/manifests/1.4", headers)
    image_digest = "tag:1.4"
    if "manifests" in manifest:
        image = next(m for m in manifest["manifests"] if m.get("platform", {}).get("os") == "linux" and m.get("platform", {}).get("architecture") == "amd64")
        image_digest = image["digest"]
        manifest = get_json(REGISTRY + "/manifests/" + image_digest, headers)
    config = get_json(REGISTRY + "/blobs/" + manifest["config"]["digest"], headers)
    layers = iter(manifest["layers"])
    database_layers = []
    for history in config.get("history", []):
        if not history.get("empty_layer", False):
            layer = next(layers)
            command = history.get("created_by", "")
            if "freshclam --foreground" in command:
                database_layers.append(layer)
    if len(database_layers) != 1:
        raise RuntimeError("Cannot unambiguously identify the official signature database layer")
    layer = database_layers[0]
    digest = layer["digest"]
    if not digest.startswith("sha256:") or len(digest) != 71 or layer["size"] > 400 * 1024 * 1024:
        raise RuntimeError("Unexpected signature layer format or size")
    archive = ROOT / "official-database-layer.tar.gz"
    print("Downloading signature layer from official clamav/clamav:1.4...", flush=True)
    expected = digest.split(":", 1)[1]
    deadline = time.monotonic() + 180
    total = 0
    checksum = hashlib.sha256()
    try:
        request = urllib.request.Request(REGISTRY + "/blobs/" + digest, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                if time.monotonic() > deadline:
                    raise RuntimeError("Signature download deadline exceeded")
                total += len(chunk)
                if total > layer["size"]:
                    raise RuntimeError("Signature layer exceeds declared size")
                checksum.update(chunk)
                output.write(chunk)
        if total != layer["size"] or checksum.hexdigest() != expected:
            raise RuntimeError("Official signature layer SHA256 verification failed")
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    print("Layer SHA256 verified. Extracting signed database files only...", flush=True)
    database = ROOT / "database"
    database.mkdir(parents=True, exist_ok=True)
    extracted = []
    total_extracted = 0
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.as_posix() not in ALLOWED_FILES:
                continue
            total_extracted += member.size
            if not member.isfile() or member.size > 350 * 1024 * 1024 or total_extracted > 700 * 1024 * 1024:
                raise RuntimeError("Unexpected signature database member")
            target = database / path.name
            temporary = database / (path.name + ".download")
            try:
                with source.extractfile(member) as content, temporary.open("wb") as output:
                    shutil.copyfileobj(content, output, 1024 * 1024)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            extracted.append(path.name)
    if not any(name.startswith("main.") for name in extracted) or not any(name.startswith("daily.") for name in extracted):
        raise RuntimeError("Official image layer did not contain the required signature databases")
    (ROOT / "database-source.json").write_text(json.dumps({
        "source": "official clamav/clamav:1.4", "image_digest": image_digest,
        "layer_digest": digest, "files": extracted,
    }, indent=2), encoding="utf-8")
    print("Installed official signed databases: " + ", ".join(extracted), flush=True)
    print("Run FreshClam regularly when its official database endpoint is reachable.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        print(f"Official image registry returned HTTP {exc.code}.")
        raise SystemExit(2)
    except (OSError, urllib.error.URLError, RuntimeError, ValueError, KeyError, StopIteration, tarfile.TarError) as exc:
        print(f"Official database bootstrap failed ({type(exc).__name__}); scanner protection remains enabled.")
        raise SystemExit(1)
