from loguru import logger
import sys
from pathlib import Path


logger_verbose = False

def loginit(verbose=False):
    global logger_verbose
    logger_verbose = verbose
    logger.remove()

    level = "DEBUG" if verbose else "INFO"

    # print("ZZZ LOGINIT", level)
    logger.add(Path("~/2gis.log").expanduser(), level="DEBUG", rotation="100 MB", compression="zip", format="{time:YYYY-MM-DD HH:mm:ss} {message}")
    logger.add(sys.stderr, level=level, format="{time:YYYY-MM-DD HH:mm:ss} {message}")

def testlogger():
    logger.debug("Debug test message")
    logger.info("Info test message")
    logger.success("Success test message")
    logger.warning("Warning test message")
    logger.error("Error test message")
    logger.critical("Critical test message")
