import itertools
import threading


class KeyRotator:
    """Thread-safe round-robin index generator over N available API keys.

    The Brain and the main Chat model can each pull their own rotating
    index so that a burst of Brain calls doesn't starve the chat calls
    of key diversity (or vice versa).
    """

    def __init__(self, key_count: int):
        self._key_count = max(key_count, 1)
        self._lock = threading.Lock()
        self._counter = itertools.count()

    def next_index(self) -> int:
        if self._key_count <= 1:
            return 0
        with self._lock:
            n = next(self._counter)
        return n % self._key_count

    @property
    def key_count(self) -> int:
        return self._key_count


def build_rotators(groq_api_keys: list) -> dict:
    """Returns independent rotators for the brain and chat call sites,
    both sized to the same key pool but ticking independently."""
    count = len(groq_api_keys) or 1
    return {
        "brain": KeyRotator(count),
        "chat": KeyRotator(count),
    }
