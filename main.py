import logging
import queue
import threading
import time
from datetime import datetime

import config
from engine.renderer import Renderer
from server import create_app

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)

SUNRISE_HOUR = 6   # day starts at 06:00
EVENING_HOUR = 17  # evening (lights on) starts at 17:00
NIGHT_HOUR   = 22  # night (dark, no lights) starts at 22:00


def _time_of_day(hour: int) -> str:
    if hour >= NIGHT_HOUR or hour < SUNRISE_HOUR:
        return "night"
    if hour >= EVENING_HOUR:
        return "evening"
    return "day"


def _day_night_scheduler(event_queue: queue.Queue):
    last_state = None
    while True:
        state = _time_of_day(datetime.now().hour)
        if state != last_state:
            event = {"day": "sunrise", "evening": "evening", "night": "night"}[state]
            logger.info("Scheduler: firing %s (hour=%d)", event, datetime.now().hour)
            event_queue.put(event)
            last_state = state
        time.sleep(60)


def main():
    event_queue: queue.Queue = queue.Queue()

    app = create_app(event_queue)

    flask_thread = threading.Thread(
        target=lambda: app.run(
            host=config.HTTP_HOST,
            port=config.HTTP_PORT,
            use_reloader=False,
        ),
        daemon=True,
        name="flask",
    )
    flask_thread.start()

    scheduler_thread = threading.Thread(
        target=_day_night_scheduler,
        args=(event_queue,),
        daemon=True,
        name="day_night_scheduler",
    )
    scheduler_thread.start()

    # pygame must run on the main thread
    renderer = Renderer(event_queue)
    renderer.run()


if __name__ == "__main__":
    main()
