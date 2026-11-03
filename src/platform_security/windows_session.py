"""Honest Windows boundary until storage ownership and WTS monitoring are ported."""

from __future__ import annotations

from platform_security.local_protection import (
    ObserverContext,
    ScreenLockUnavailable,
    ScreenState,
)


class WindowsSessionAdapter:
    """No OS request is allowed without the missing trusted WTS event path.

    The existing application imports POSIX Linux recovery and requires fcntl
    ownership locking. Implementing a Windows application port here would exceed
    the requested adapter boundary. LockWorkStation return success alone must
    never be used as screen-lock evidence.
    """

    unavailable_code = "windows_port_required"

    @property
    def screen_context(self) -> ObserverContext | None:
        return None

    @property
    def sleep_context(self) -> ObserverContext | None:
        return None

    async def read_screen_state(self, context: ObserverContext) -> ScreenState:
        raise ScreenLockUnavailable(self.unavailable_code)

    async def request_screen_lock(self, context: ObserverContext) -> None:
        raise ScreenLockUnavailable(self.unavailable_code)
