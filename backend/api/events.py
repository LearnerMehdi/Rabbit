"""Server-sent events: book progress and library changes, published from any thread."""
import asyncio
import json
import threading
from typing import Callable

from starlette.requests import Request

Listener = Callable[[str, dict], None]


class EventBus:
    def __init__(self):
        self._listeners: set[Listener] = set()
        self._lock = threading.Lock()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.add(listener)
        return lambda: self.unsubscribe(listener)

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def publish(self, event: str, data: dict) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener(event, data)

    async def stream(self, request: Request, ping_s: float = 15.0):
        """`text/event-stream` body for one client, until it disconnects."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        unsubscribe = self.subscribe(lambda e, d: loop.call_soon_threadsafe(queue.put_nowait, (e, d)))
        try:
            yield "retry: 2000\n\n"
            while not await request.is_disconnected():
                try:
                    event, data = await asyncio.wait_for(queue.get(), ping_s)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
        finally:
            unsubscribe()
