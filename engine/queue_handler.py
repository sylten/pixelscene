import queue
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class QueueHandler:
    def __init__(self, event_queue: queue.Queue, on_event: Callable[[str], None]):
        self._queue = event_queue
        self._on_event = on_event

    def poll(self):
        try:
            event_name = self._queue.get_nowait()
            logger.info("Dequeued event: %s", event_name)
            self._on_event(event_name)
        except queue.Empty:
            pass
