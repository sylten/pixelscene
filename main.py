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

NIGHT_HOUR   = 17  # fire night_fall at or after this hour
SUNRISE_HOUR =  6  # fire sunrise at or after this hour


def _is_night(hour: int) -> bool:
    return hour >= NIGHT_HOUR or hour < SUNRISE_HOUR


def _day_night_scheduler(event_queue: queue.Queue):
    last_state = None
    while True:
        hour = datetime.now().hour
        state = "night" if _is_night(hour) else "day"
        if state != last_state:
            event = "night_fall" if state == "night" else "sunrise"
            logger.info("Scheduler: firing %s (hour=%d)", event, hour)
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
