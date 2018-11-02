import logging
from logging.handlers import RotatingFileHandler

__all__ = ['get_logger', 'log_configurer']


def get_logger(name=None):
    return logging.getLogger(name)


def log_configurer(verbose=True, logfile=None):
    if verbose or logfile:
        formatter = logging.Formatter(fmt='%(message)s')
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        if verbose:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)
        if logfile:
            file_handler = RotatingFileHandler(
                logfile, maxBytes=20971520, backupCount=10)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
