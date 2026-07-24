"""Sync twin of ``storix._async._compat`` - hand-written, NOT generated.

Call sites hand their work to ``concurrent`` as *thunks* (zero-arg
callables, built with ``functools.partial``); the sync flavor dispatches
them to a bounded ``ThreadPoolExecutor``, which gives genuine I/O
concurrency because the sync backends do GIL-releasing blocking I/O
(``os``, the non-aio Azure SDK, ``opendal.Operator``). Passing thunks
*un-invoked* is what lets sync defer the work to threads instead of
computing every result eagerly during argument evaluation.

Error semantics match the async twin: results are collected in submission
order, so the first exception *in order* propagates unwrapped (no
``ExceptionGroup``) and the storix taxonomy survives ``except
PathNotFoundError``. Teardown does not join: queued thunks are cancelled
and in-flight thunks are abandoned, so a Ctrl+C mid-transfer returns to
the prompt at once instead of waiting out the remaining work. That is the
async behavior too, where ``gather`` documents "Remaining tasks run to
completion in the background".

Keep in lockstep with the async twin; both are excluded from codegen.
"""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

from storix.constants import DEFAULT_CONCURRENCY


def concurrent[T](
    thunks: Iterable[Callable[[], T]], *, limit: int = DEFAULT_CONCURRENCY
) -> list[T]:
    """Run each thunk in a bounded thread pool, results in submission order.

    A thunk is a zero-arg callable returning its result directly. At most
    ``limit`` run at once; empty input yields ``[]``. See the module
    docstring for the error semantics.
    """
    thunk_list = list(thunks)  # may be a generator; materialize once
    if not thunk_list:
        return []
    executor = ThreadPoolExecutor(max_workers=limit)
    try:
        futures = [executor.submit(thunk) for thunk in thunk_list]
        return [future.result() for future in futures]
    finally:
        # never join on teardown: a Ctrl+C mid-transfer must return to the
        # prompt now, and the not-yet-started thunks must not start
        executor.shutdown(wait=False, cancel_futures=True)
