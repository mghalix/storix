import datetime as dt
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, SecretStr


class StorixBaseModel(BaseModel):
    """Base model for Storix data models."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
        json_encoders={
            # custom output conversion for datetime
            dt.datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if v else None,
            SecretStr: lambda v: v.get_secret_value() if v else None,
        },
    )


class AzureFileProperties(StorixBaseModel):
    """Properties for Azure Data Lake files and directories."""

    name: str
    hdi_isfolder: bool = False
    last_modified: dt.datetime
    creation_time: dt.datetime
