import logging
import logging.handlers


# Copied from https://stackoverflow.com/questions/37958568/how-to-implement-a-global-python-logger
def init_logger(name, level: str):
    # logger settings
    if logging.getLevelName(level) is logging.DEBUG:
        log_format = "%(asctime)s [%(levelname)s] %(filename)s(%(funcName)s:%(lineno)s): %(message)s"
    else:
        log_format = "%(asctime)s [%(levelname)s] %(module)s: %(message)s"
    formatter = logging.Formatter(log_format)

    # setup logger
    logger = logging.getLogger(name)
    logger.level = logging.getLevelName(level)

    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(formatter)

    logger.addHandler(streamhandler)

    return logger
