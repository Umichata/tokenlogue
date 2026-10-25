"""Переносит принадлежность сервисного вызова через await и SQLite workers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def repository_session(
    attribute: str,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]
]:
    def decorate(
        function: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(function)
        async def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
            repository = getattr(args[0], attribute)
            access = getattr(repository, "access", None)
            if access is None:
                return await function(*args, **kwargs)
            with access.session():
                return await function(*args, **kwargs)

        return invoke

    return decorate


async def finish_worker(work: Coroutine[Any, Any, R]) -> R:
    """Не освобождает lease, пока отменённый SQLite worker ещё выполняется."""
    task = asyncio.create_task(work)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError()
    return result


async def await_task_completion(task: asyncio.Task[R]) -> R:
    """После отмены владельца дожидается worker вопреки повторным отменам."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()
