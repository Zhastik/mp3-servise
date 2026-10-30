"""HTTP-specific byte-range responses for decrypted audio."""
import re

from fastapi.responses import Response


def build_audio_response(data: bytes, range_header: str | None = None, head: bool = False) -> Response:
    size = len(data)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store",
               "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"}
    start, end, status_code = 0, size - 1, 200

    def unsatisfiable() -> Response:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})

    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip()) if len(range_header) <= 100 else None
        if not match or not any(match.groups()) or size == 0:
            return unsatisfiable()
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            suffix = int(last)
            if suffix == 0:
                return unsatisfiable()
            start = max(0, size - suffix)
        if start >= size or start > end:
            return unsatisfiable()
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return Response(b"" if head else data[start:end + 1], status_code=status_code,
                    media_type="audio/mpeg", headers=headers)
