"""Request-local, fixed-name performance counters; no source identifiers."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

_active = ContextVar("quasar_timings", default=None)
NAMES = frozenset(("source", "prepare", "query", "encode", "compress", "upstream"))


@contextmanager
def collect():
    samples = {}
    token = _active.set(samples)
    try:
        yield samples
    finally:
        _active.reset(token)


@contextmanager
def phase(name):
    if name not in NAMES:
        raise ValueError("Unknown timing phase")
    start = perf_counter()
    try:
        yield
    finally:
        samples = _active.get()
        if samples is not None:
            samples[name] = samples.get(name, 0) + (perf_counter() - start) * 1000


def header():
    return ", ".join(f"{name};dur={duration:.2f}" for name, duration in sorted((_active.get() or {}).items()))
