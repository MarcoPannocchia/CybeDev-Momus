import asyncio
import functools
import time


def timed(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            wrapper.last_duration = time.perf_counter() - started

    wrapper.last_duration = None
    return wrapper


def memoize(func):
    cache = {}

    @functools.wraps(func)
    def wrapper(*args):
        if args not in cache:
            cache[args] = func(*args)
        return cache[args]

    wrapper.cache = cache
    return wrapper


@timed
async def gather_limited(factories, limit=3):
    semaphore = asyncio.Semaphore(limit)

    async def run(factory):
        async with semaphore:
            return await factory()

    return await asyncio.gather(*(run(factory) for factory in factories))


@memoize
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
