import logging
import logging.handlers


# Copied from https://stackoverflow.com/questions/37958568/how-to-implement-a-global-python-logger
def init_logger(name, level: str):
    # logger settings
    log_file = "log/bot.log"
    log_file_max_size = 1024 * 1024 * 20  # megabytes
    log_num_backups = 5
    if logging.getLevelName(level) is logging.DEBUG:
        log_format = u"%(asctime)s [%(levelname)s] %(filename)s(%(funcName)s:%(lineno)s): %(message)s"
    else:
        log_format = u"%(asctime)s [%(levelname)s] %(module)s: %(message)s"
    formatter = logging.Formatter(log_format)

    # setup logger
    logger = logging.getLogger(name)
    logger.level = logging.getLevelName(level)

    filehandler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=log_file_max_size, backupCount=log_num_backups, encoding='utf-8'
    )
    filehandler.setFormatter(formatter)

    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(formatter)

    logger.addHandler(filehandler)
    logger.addHandler(streamhandler)

    return logger
