import logging
import os
from logging.handlers import RotatingFileHandler

LOGGER_DIR = './logs'
LOGGER_FILENAME = 'app.log'
LOGGER_FILEPATH = f'{LOGGER_DIR}/{LOGGER_FILENAME}'
LOGGER_INSTANCE_NAME = 'supertrend-algo-bot'


def logger_setup():
    if not os.path.isdir(LOGGER_DIR):
        os.mkdir(LOGGER_DIR)

    if not os.path.isfile(LOGGER_FILEPATH):
        with open(LOGGER_FILEPATH, 'w+'):
            pass

    # Create a logger instance
    logger = logging.getLogger(LOGGER_INSTANCE_NAME)
    logger.setLevel(logging.INFO)

    # Define the log format
    log_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    # Create a rotating file handler
    file_handler = RotatingFileHandler(
        LOGGER_FILEPATH, maxBytes=10*1024*1024, backupCount=10)
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # Create a stream handler to display logs in the console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger
