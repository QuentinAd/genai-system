import logging
from functools import wraps

from pydantic import ValidationError
from quart import jsonify, request
from werkzeug.exceptions import BadRequest

logger = logging.getLogger(__name__)


def validate(model):
    """Validate incoming JSON data against a Pydantic model."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                payload = await request.get_json()
                if payload is None:
                    raise BadRequest()
                data = model(**payload)
            except (ValidationError, BadRequest, Exception):  # pragma: no cover - simple example
                logger.exception("Invalid request data")
                return jsonify({"error": "Invalid request data"}), 400
            return await func(data, *args, **kwargs)

        return wrapper

    return decorator


def log_call(func):
    """Log function calls."""

    logger_func = logging.getLogger(func.__module__)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger_func.info("Calling %s", func.__name__)
        return await func(*args, **kwargs)

    return wrapper
