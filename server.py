import logging
import queue

from flask import Flask, jsonify, request

import config

logger = logging.getLogger(__name__)


def create_app(event_queue: queue.Queue) -> Flask:
    app = Flask(__name__)

    @app.route("/event", methods=["POST"])
    def handle_event():
        data = request.get_json(silent=True) or {}
        event_name = data.get("event")
        if not event_name:
            logger.warning("POST /event received with no 'event' field")
            return "", 204
        logger.info("Queuing event: %s", event_name)
        event_queue.put(event_name)
        return "", 204

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "scene": config.DEFAULT_SCENE,
            "queue_depth": event_queue.qsize(),
        })

    return app
