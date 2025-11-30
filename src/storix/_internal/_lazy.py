import inspect

from typing import Any, Literal, overload


try:
    import wrapt
except ImportError as err:
    msg = 'storix lazy imports require the core extra; run `uv add "storix[core]"`'
    raise ImportError(msg) from err


# NOTE: use lazy import only to import non-type objects that needn't to be used
# for instance checks, as the lazy proxy could mess it up when first accessed.
@overload
def lazy_import(module: str, /) -> Any:
    """import module."""


@overload
def lazy_import(relative: Literal['.'], module: str, /) -> Any:
    """from . import module"""


@overload
def lazy_import(module: str, attr: str, /) -> Any:
    """from module import attr."""


def lazy_import(
    name: str,
    attr: str | None = None,
    /,
    **kwargs: Any,
) -> Any:
    if name.startswith('.'):
        return _lazy_import_relative(name, attr)
    if attr is None:
        return _lazy_import_absolute(name, attribute=None, **kwargs)
    return _lazy_import_absolute(name, attribute=attr, **kwargs)


def _lazy_import_absolute(
    name: str, attribute: str | None = None, **kwargs: Any
) -> Any:
    return wrapt.lazy_import(
        name,
        *([] if attribute is None else [attribute]),  # silent wrapt's overloads
        **kwargs,
    )


def _lazy_import_relative(
    mod: str,
    /,
    attr: str | None = None,
    **kwargs: Any,
) -> Any:
    frame = inspect.currentframe()
    # storix/_internal/_lazy.py  # so two steps back to reach root
    if frame is None or frame.f_back is None or frame.f_back.f_back is None:
        msg = "lazyimport: unable to inspect caller's frame"
        raise RuntimeError(msg)

    caller_frame = frame.f_back.f_back
    pkg = caller_frame.f_globals.get('__package__')
    if not pkg:
        msg = 'lazyimport: relative imports require a package context'
        raise RuntimeError(msg)

    suffix = mod.lstrip('.')

    if suffix:
        base = f'{pkg}.{suffix}'
        if attr is not None:
            return wrapt.lazy_import(base, attr, **kwargs)
        return wrapt.lazy_import(base, **kwargs)

    if attr is None:
        return wrapt.lazy_import(pkg, **kwargs)

    base = f'{pkg}.{attr}'
    return wrapt.lazy_import(base, **kwargs)


_limp = lazy_import

__all__ = ('_limp',)
