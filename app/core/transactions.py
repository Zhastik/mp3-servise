"""Use-case transaction boundary; repositories never commit independently."""
from contextlib import asynccontextmanager
from typing import Protocol


class TransactionalSession(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


@asynccontextmanager
async def transaction(session: TransactionalSession):
    """Reuse the request session, including its existing read transaction."""
    try:
        yield
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
