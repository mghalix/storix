from ._base import Storage
from .azure import AzureDataLake
from .local import LocalFilesystem

providers: list[type[Storage]] = [
    AzureDataLake,
    LocalFilesystem,
]

__all__ = ["AzureDataLake", "LocalFilesystem", "Storage"]
