import logging
import queue
import threading

import config
from engine.renderer import Renderer
from server import create_app

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


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

    # pygame must run on the main thread
    renderer = Renderer(event_queue)
    renderer.run()


if __name__ == "__main__":
    main()
