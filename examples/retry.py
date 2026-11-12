import time


def retry(func, attempts=3, delay=0.5, exceptions=(Exception,)):
    last_error = None
    for attempt in range(attempts):
        try:
            return func()
        except exceptions as error:
            last_error = error
            time.sleep(delay * (2 ** attempt))
    raise last_error
