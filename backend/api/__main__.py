"""Run the app: python -m api (host and port from config.yaml). Started by ../start.sh."""
import logging

import uvicorn

import config

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(f"Orange Reader: http://{config.HOST}:{config.PORT}", flush=True)
    uvicorn.run("api.app:app", host=config.HOST, port=config.PORT, log_level="info")
