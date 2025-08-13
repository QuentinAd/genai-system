from . import create_app
import logging

# Configure root/app loggers for container visibility
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

app = create_app()

if __name__ == "__main__":
    app.run()
