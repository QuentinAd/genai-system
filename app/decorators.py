from functools import wraps
import logging
from quart import jsonify, request


def validate(model):
    """Validate incoming JSON data against a Pydantic model."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                data = model(**(await request.get_json(force=True)))
            except Exception as exc:  # pragma: no cover - simple example
                return jsonify({"error": str(exc)}), 400
            return await func(data, *args, **kwargs)

        return wrapper

    return decorator


def log_call(func):
    """Log function calls with method and path."""

    logger = logging.getLogger("app")

    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info("Calling %s %s %s", func.__name__, request.method, request.path)
        return await func(*args, **kwargs)

    return wrapper
