from loguru import logger
import sys
from pathlib import Path



def loginit(level: str = "INFO"):
    logger.remove()
    
    logger.add(Path("~/2gis.log").expanduser(), level="DEBUG", rotation="100 MB", compression="zip", format="{time:YYYY-MM-DD HH:mm:ss} {message}")
    logger.add(sys.stderr, level=level, format="{time:YYYY-MM-DD HH:mm:ss} {message}")

def testlogger():
    logger.debug("Debug message")
    logger.info("Info message")
    logger.success("Success message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
