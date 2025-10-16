"""Async storage provider package exports."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ._proto import Storage

if TYPE_CHECKING:
    from .azure import AzureDataLake
    from .local import LocalFilesystem

__all__ = ["AzureDataLake", "LocalFilesystem", "Storage"]

_module_lookup = {
    "AzureDataLake": "storix.aio.providers.azure",
    "LocalFilesystem": "storix.aio.providers.local",
}


def __getattr__(name: str) -> Any:
    if name in _module_lookup:
        module = importlib.import_module(_module_lookup[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__} has no attribute {name}")
