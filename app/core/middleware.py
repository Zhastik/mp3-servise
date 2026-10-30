"""Same-origin writes, bounded request bodies, and browser security headers."""
import asyncio
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from app.core.config import settings


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.maximum = (settings.MAX_UPLOAD_MB + 1) * 1024 * 1024
        self.body_slots = asyncio.Semaphore(4)
        self.stream_slots = asyncio.Semaphore(4)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}

        async def secure_send(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin"),
                    (b"x-frame-options", b"DENY"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                if scope["path"] == "/" or scope["path"].startswith("/static/"):
                    extra.append((b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"))
                if scope["path"].startswith(("/auth/", "/api/")):
                    existing = {k.lower() for k, _ in message.get("headers", [])}
                    if b"cache-control" not in existing:
                        extra.append((b"cache-control", b"no-store"))
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message = {**message, "headers": list(message.get("headers", [])) + [(k, v) for k, v in extra if k not in existing]}
            await send(message)

        async def reject(code, message):
            await JSONResponse({"detail": message}, status_code=code)(scope, receive, secure_send)

        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = headers.get("origin")
            if origin:
                try:
                    parsed = urlsplit(origin)
                except ValueError:
                    return await reject(403, "Некорректный источник запроса")
                if parsed.netloc.lower() != headers.get("host", "").lower() or parsed.scheme != scope.get("scheme", "http"):
                    return await reject(403, "Запрос с другого сайта отклонён")
            if headers.get("sec-fetch-site") == "cross-site":
                return await reject(403, "Запрос с другого сайта отклонён")
            try:
                declared = int(headers.get("content-length", "0"))
            except ValueError:
                return await reject(400, "Некорректный размер запроса")
            maximum = self.maximum if scope["path"] == "/api/tracks" else 64 * 1024
            if declared > maximum or declared < 0:
                return await reject(413, "Слишком большой запрос")
            try:
                await asyncio.wait_for(self.body_slots.acquire(), timeout=2)
            except TimeoutError:
                return await reject(429, "Сервис занят. Повторите запрос позже")
            try:
                messages, total = [], 0
                try:
                    async with asyncio.timeout(60):
                        while True:
                            message = await receive()
                            if message["type"] == "http.disconnect":
                                return
                            total += len(message.get("body", b""))
                            if total > maximum:
                                return await reject(413, "Слишком большой запрос")
                            messages.append(message)
                            if not message.get("more_body", False):
                                break
                except TimeoutError:
                    return await reject(408, "Истекло время передачи файла")
                iterator = iter(messages)

                async def replay():
                    return next(iterator, None) or await receive()

                return await self.app(scope, replay, secure_send)
            finally:
                self.body_slots.release()
        if scope["path"].startswith("/api/tracks/") and scope["path"].endswith("/stream"):
            try:
                await asyncio.wait_for(self.stream_slots.acquire(), timeout=3)
            except TimeoutError:
                return await reject(429, "Плеер занят. Повторите воспроизведение позже")
            try:
                return await self.app(scope, receive, secure_send)
            finally:
                self.stream_slots.release()
        return await self.app(scope, receive, secure_send)
