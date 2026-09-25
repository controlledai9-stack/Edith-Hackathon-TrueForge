import functools
import logging
import time

logger = logging.getLogger("J.A.R.V.I.S")


def retry(times: int = 2, delay: float = 0.6, backoff: float = 2.0, exceptions=(Exception,)):
    """Retry a function call on exception, with exponential backoff.

    Usage:
        @retry(times=3, delay=0.5)
        def call_api(...): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            wait = delay
            for attempt in range(1, times + 2):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt > times:
                        break
                    logger.warning(
                        "[RETRY] %s failed (attempt %d/%d): %s",
                        fn.__name__, attempt, times + 1, e,
                    )
                    time.sleep(wait)
                    wait *= backoff
            raise last_exc
        return wrapper
    return decorator


async def async_retry_call(coro_fn, *args, times: int = 2, delay: float = 0.6,
                            backoff: float = 2.0, exceptions=(Exception,), **kwargs):
    """Async equivalent: await async_retry_call(some_async_fn, arg1, arg2)."""
    import asyncio
    last_exc = None
    wait = delay
    for attempt in range(1, times + 2):
        try:
            return await coro_fn(*args, **kwargs)
        except exceptions as e:
            last_exc = e
            if attempt > times:
                break
            logger.warning(
                "[RETRY] %s failed (attempt %d/%d): %s",
                getattr(coro_fn, "__name__", "call"), attempt, times + 1, e,
            )
            await asyncio.sleep(wait)
            wait *= backoff
    raise last_exc
