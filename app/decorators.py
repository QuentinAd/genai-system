from functools import wraps
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
    """Log function calls."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        return await func(*args, **kwargs)

    return wrapper
