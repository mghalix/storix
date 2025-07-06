import os
from typing import Literal

PathLike = os.PathLike | str
AvailableProviders = Literal["local", "azure"]
