from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from storix.types import AvailableProviders


def find_env_file() -> str | None:
    """Find .env file in current directory or parent directories."""
    current = Path.cwd()

    # Search current directory and all parent directories
    while current != current.parent:
        env_file = current / '.env'
        if env_file.exists():
            return str(env_file)
        current = current.parent

    # Also check user's home directory
    home_env = Path.home() / '.storix' / '.env'
    if home_env.exists():
        return str(home_env)

    return None


class Settings(BaseSettings):
    """Application settings for storage providers and environment configuration."""

    STORAGE_PROVIDER: AvailableProviders = 'local'

    STORAGE_INITIAL_PATH: str = '.'
    STORAGE_INITIAL_PATH_LOCAL: str = STORAGE_INITIAL_PATH
    STORAGE_INITIAL_PATH_AZURE: str = STORAGE_INITIAL_PATH

    # TODO: implement Storage Pool
    # STORAGE_POOL_MAX_CONNECTIONS: int = 10

    # TODO: separate into modular settings for each provider
    # or prefix with STORAGE like above for consistent environment

    # Azure Data Lake Gen2
    ADLSG2_CONTAINER_NAME: str | None = None
    ADLSG2_ACCOUNT_NAME: str | None = None
    ADLSG2_TOKEN: str | None = None
    ADLSG2_ALLOW_CONTAINER_NAME_IN_PATHS: bool | None = None

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=True,
    )


def get_settings() -> Settings:
    """Get storix settings."""
    return Settings()
