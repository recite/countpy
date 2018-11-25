import logging
from logging.handlers import RotatingFileHandler, QueueHandler
from multiprocessing import Process

__all__ = ['get_logger', 'client_configurer', 'LogServer']

MAX_FILE_SIZE = 20971520
LOG_FILE_COUNT = 10


def get_logger(name=None):
    return logging.getLogger(name)


def server_configurer(verbose=True, logfile=None):
    if verbose or logfile:
        root = logging.getLogger()
        formatter = logging.Formatter(
            fmt='%(asctime)s %(processName)-10s : %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        if verbose:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)
        if logfile:
            file_handler = RotatingFileHandler(
                logfile, maxBytes=MAX_FILE_SIZE, backupCount=LOG_FILE_COUNT)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)


def client_configurer(queue):
    handler = QueueHandler(queue)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class LogServer(Process):
    def __init__(self, queue, verbose=True, logfile=None):
        super(LogServer, self).__init__()
        self.queue = queue
        self.verbose = verbose
        self.logfile = logfile

    def run(self):
        server_configurer(self.verbose, self.logfile)
        try:
            while True:
                try:
                    record = self.queue.get()
                    if record is None:
                        break
                    logger = logging.getLogger(record.name)
                    logger.handle(record)
                except Exception:
                    import sys, traceback
                    print('Whoops! Problem:', file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
        except KeyboardInterrupt:
            pass
