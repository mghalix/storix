import os
from typing import Literal

StrPathLike = os.PathLike[str] | str
AvailableProviders = Literal["local", "azure"]
