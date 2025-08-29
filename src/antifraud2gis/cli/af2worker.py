import dramatiq
import sys
import redis
import time
from ..const import REDIS_WORKER_STARTED
from ..tasks import fraud_task, set_status
from dramatiq.cli import main as dramatiq_main
from ..logger import logger, loginit

"""
af2worker antifraud2gis.tasks
"""
def main():


    r = redis.Redis(
        decode_responses=True
    )


    sys.argv = ["dramatiq", "-p1", "-t1", "antifraud2gis.tasks"]
    loglevel = "DEBUG" # (or "INFO")
    loginit(loglevel)
    logger.debug(f"Starting dramatiq worker ({loglevel})")

    set_status("worker started")
    r.set(REDIS_WORKER_STARTED, time.time())

    dramatiq_main()

if __name__ == "__main__":
    main()
