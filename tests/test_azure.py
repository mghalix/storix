import contextlib
import os

from collections.abc import Generator
from datetime import UTC, datetime as dt
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from storix import AzureDataLake, Storage
from storix.types import StorixPath


def create_mock_properties(
    name: str, is_folder: bool = False, **extra_props: Any
) -> MagicMock:
    """Create a mock properties object that works with FileProperties validation."""
    base_props = {
        'name': name,
        'hdi_isfolder': is_folder,
        'last_modified': dt.now(tz=UTC),
        'creation_time': dt.now(tz=UTC),
        **extra_props,
    }

    # Create a mock that behaves like Azure properties
    mock_props = MagicMock()
    # Set attributes on the mock so they can be accessed via **props
    for key, value in base_props.items():
        setattr(mock_props, key, value)

    # Mock the get method for metadata access
    mock_props.get.return_value = {}  # Empty metadata

    # Make the mock iterable for **props unpacking
    mock_props.__iter__ = lambda: iter(base_props.keys())
    mock_props.__getitem__ = lambda self, key: base_props[key]
    mock_props.keys = lambda: base_props.keys()
    mock_props.items = lambda: base_props.items()
    mock_props.values = lambda: base_props.values()

    return mock_props


# Mock Azure dependencies to avoid requiring actual credentials for basic tests
@pytest.fixture
def mock_azure_clients() -> Generator[Any]:
    """Mock Azure clients to avoid requiring real credentials."""
    with (
        patch('storix.providers.azure.DataLakeServiceClient') as mock_service,
        patch('storix.utils.magic') as mock_magic,
    ):
        # Mock service client
        mock_service_instance = MagicMock()
        mock_service.return_value = mock_service_instance

        # Mock filesystem client
        mock_filesystem = MagicMock()
        mock_service_instance.get_file_system_client.return_value = mock_filesystem
        mock_service_instance.create_file_system.return_value = mock_filesystem

        # Mock magic library
        mock_magic.from_buffer.return_value = 'text/plain'

        yield {
            'service': mock_service_instance,
            'filesystem': mock_filesystem,
            'magic': mock_magic,
        }


@pytest.fixture
def azure_storage(mock_azure_clients: Any) -> Storage:
    """Create an AzureDataLake instance with mocked clients."""
    return AzureDataLake(
        initialpath='/',
        container_name='test-container',
        adlsg2_account_name='test_account',
        adlsg2_token='test_token',
        sandboxed=False,
    )


@pytest.fixture
def sandboxed_azure_storage(mock_azure_clients: Any) -> Storage:
    """Create a sandboxed AzureDataLake instance."""
    return AzureDataLake(
        initialpath='/test',
        container_name='test-container',
        adlsg2_account_name='test_account',
        adlsg2_token='test_token',
        sandboxed=True,
    )


# Test initialization
def test_azure_init_success(mock_azure_clients: Any) -> None:
    """Test successful Azure Data Lake initialization."""
    storage = AzureDataLake(
        adlsg2_account_name='test_account', adlsg2_token='test_token'
    )
    assert isinstance(storage, AzureDataLake)


def test_azure_init_missing_credentials() -> None:
    """Test Azure Data Lake initialization fails without credentials."""
    with pytest.raises(
        AssertionError,
        match='ADLSg2 account name and authentication token are required',
    ):
        AzureDataLake(adlsg2_account_name=None, adlsg2_token='token')

    with pytest.raises(
        AssertionError,
        match='ADLSg2 account name and authentication token are required',
    ):
        AzureDataLake(adlsg2_account_name='account', adlsg2_token=None)


def test_azure_init_from_settings(mock_azure_clients: Any) -> None:
    """Test initialization using settings."""
    with patch('storix.providers.azure.settings') as mock_settings:
        mock_settings.ADLSG2_ACCOUNT_NAME = 'settings_account'
        mock_settings.ADLSG2_TOKEN = 'settings_token'
        mock_settings.ADLSG2_CONTAINER_NAME = 'settings_container'

        storage = AzureDataLake(
            adlsg2_account_name='settings_account',
            adlsg2_token='settings_token',
            container_name='settings_container',
        )
        assert isinstance(storage, AzureDataLake)


# Test properties
def test_root_property(azure_storage: Storage) -> None:
    """Test root property returns home path."""
    assert azure_storage.root == azure_storage.home


def test_pwd(azure_storage: Storage) -> None:
    """Test pwd returns current path."""
    current = azure_storage.pwd()
    assert isinstance(current, StorixPath)


# Test directory operations
def test_cd(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cd functionality."""
    # Mock stat to return directory properties
    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Test cd to valid directory
    result = azure_storage.cd('/test')
    assert result == azure_storage
    assert azure_storage.pwd() == Path('/test')


def test_cd_to_home(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cd with None goes to home directory."""
    # Mock home directory properties
    mock_props = create_mock_properties('', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    original_home = azure_storage.home
    azure_storage.cd(None)
    assert azure_storage.pwd() == original_home


def test_cd_to_file_fails(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cd to file raises error."""
    # Mock stat to return file properties
    mock_props = create_mock_properties('test.txt', is_folder=False)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with pytest.raises(ValueError, match='cd: not a directory'):
        azure_storage.cd('/test.txt')


def test_cd_nonexistent_path(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cd to nonexistent path raises error."""
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = False

    mock_dir_client = MagicMock()
    mock_dir_client.exists.return_value = False

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client

    with pytest.raises(ValueError, match='path .* does not exist'):
        azure_storage.cd('/nonexistent')


# Test listing operations
def test_ls(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test ls functionality."""
    # Mock directory exists
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock get_paths return
    mock_path1 = MagicMock()
    mock_path1.name = 'file1.txt'
    mock_path2 = MagicMock()
    mock_path2.name = 'dir1'

    mock_azure_clients['filesystem'].get_paths.return_value = [mock_path1, mock_path2]

    # Test relative names
    result = azure_storage.ls('/test')
    assert 'file1.txt' in result
    assert 'dir1' in result


def test_ls_abs(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test ls with abs=True."""
    # Mock directory exists
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock get_paths return
    mock_path1 = MagicMock()
    mock_path1.name = 'file1.txt'

    mock_azure_clients['filesystem'].get_paths.return_value = [mock_path1]

    # Test absolute paths
    result = azure_storage.ls('/test', abs=True)
    assert len(result) == 1
    assert isinstance(result[0], Path | StorixPath)


def test_ls_nonexistent_path(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test ls on nonexistent path raises error."""
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = False

    mock_dir_client = MagicMock()
    mock_dir_client.exists.return_value = False

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client

    with pytest.raises(ValueError, match='path .* does not exist'):
        azure_storage.ls('/nonexistent')


# Test file operations
def test_touch(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test touch functionality."""
    mock_file_client = MagicMock()
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    result = azure_storage.touch('/test.txt')
    assert result is True
    mock_file_client.create_file.assert_called_once()


def test_touch_with_data(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test touch with data."""
    mock_file_client = MagicMock()
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    test_data = b'hello world'
    result = azure_storage.touch('/test.txt', test_data)

    assert result is True
    mock_file_client.create_file.assert_called_once()
    mock_file_client.upload_data.assert_called_once()


def test_cat(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cat functionality."""
    # Mock file exists and is not directory
    mock_props = create_mock_properties('test.txt', is_folder=False)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    # Mock download
    mock_download = MagicMock()
    mock_download.readall.return_value = b'file content'
    mock_file_client.download_file.return_value = mock_download

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    result = azure_storage.cat('/test.txt')
    assert result == b'file content'


def test_cat_directory_fails(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cat on directory fails."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with pytest.raises(ValueError, match='cat: .* Is a directory'):
        azure_storage.cat('/testdir')


def test_cat_nonexistent(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cat on nonexistent file raises error."""
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = False

    mock_dir_client = MagicMock()
    mock_dir_client.exists.return_value = False

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client

    with pytest.raises(ValueError, match='path .* does not exist'):
        azure_storage.cat('/nonexistent.txt')


def test_rm(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test rm functionality."""
    mock_file_client = MagicMock()
    mock_props = create_mock_properties('test.txt', is_folder=False)
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    result = azure_storage.rm('/test.txt')
    assert result is True
    mock_file_client.delete_file.assert_called_once()


def test_cp_file(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test cp functionality for files."""
    # Mock file properties

    mock_props = create_mock_properties('test', is_folder=False)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    # Mock download for cat operation
    mock_download = MagicMock()
    mock_download.readall.return_value = b'file content'
    mock_file_client.download_file.return_value = mock_download

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    azure_storage.cp('/source.txt', '/dest.txt')

    # Should call create_file for destination
    assert mock_file_client.create_file.call_count >= 1


def test_mv_file(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test mv functionality for files."""
    # Mock file properties

    mock_props = create_mock_properties('test', is_folder=False)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    # Mock download for cat operation
    mock_download = MagicMock()
    mock_download.readall.return_value = b'file content'
    mock_file_client.download_file.return_value = mock_download

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    azure_storage.mv('/source.txt', '/dest.txt')

    # Should call create_file for destination and delete_file for source
    assert mock_file_client.create_file.call_count >= 1
    assert mock_file_client.delete_file.call_count >= 1


def test_mv_directory_not_implemented(
    azure_storage: Storage, mock_azure_clients: Any
) -> None:
    """Test mv for directories raises NotImplementedError."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with pytest.raises(
        NotImplementedError, match='mv is not yet supported for directories'
    ):
        azure_storage.mv('/sourcedir', '/destdir')


# Test directory operations
def test_mkdir(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test mkdir functionality."""
    mock_azure_clients['filesystem'].create_directory.return_value = None

    azure_storage.mkdir('/newdir')
    mock_azure_clients['filesystem'].create_directory.assert_called_once_with('/newdir')


def test_rmdir(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test rmdir functionality."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_dir_client = MagicMock()
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock empty directory
    mock_azure_clients['filesystem'].get_paths.return_value = []

    result = azure_storage.rmdir('/testdir')
    assert result is True
    mock_dir_client.delete_directory.assert_called_once()


def test_rmdir_non_empty_fails(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test rmdir on non-empty directory fails without recursive."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_dir_client = MagicMock()
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock non-empty directory
    mock_path = MagicMock()
    mock_path.name = 'file.txt'
    mock_azure_clients['filesystem'].get_paths.return_value = [mock_path]

    result = azure_storage.rmdir('/testdir')
    assert result is False


def test_rmdir_recursive(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test rmdir with recursive=True."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_dir_client = MagicMock()
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock non-empty directory
    mock_path = MagicMock()
    mock_path.name = 'file.txt'
    mock_azure_clients['filesystem'].get_paths.return_value = [mock_path]

    result = azure_storage.rmdir('/testdir', recursive=True)
    assert result is True
    mock_dir_client.delete_directory.assert_called_once()


def test_rmdir_file_fails(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test rmdir on file fails."""
    # Mock file properties

    mock_props = create_mock_properties('test', is_folder=False)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with pytest.raises(ValueError, match='rmdir: failed to remove .* Not a directory'):
        azure_storage.rmdir('/test.txt')


# Test file system checks
def test_exists_file(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test exists for file."""
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock path.is_file() to return True
    with patch.object(Path, 'is_file', return_value=True):
        result = azure_storage.exists('/test.txt')
        assert result is True


def test_exists_directory(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test exists for directory."""
    # Mock file client to fail first (as exists tries file client first)
    mock_file_client = MagicMock()
    mock_file_client.exists.side_effect = Exception('File not found')
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock directory client to succeed
    mock_dir_client = MagicMock()
    mock_dir_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client

    result = azure_storage.exists('/testdir')
    assert result is True


def test_exists_root(azure_storage: Storage) -> None:
    """Test exists for root always returns True."""
    result = azure_storage.exists('/')
    assert result is True


def test_exists_false(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test exists returns False for non-existent paths."""
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = False
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with patch.object(Path, 'is_file', return_value=True):
        result = azure_storage.exists('/nonexistent.txt')
        assert result is False


def test_isdir(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test isdir functionality."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    result = azure_storage.isdir('/testdir')
    assert result is True


def test_isfile(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test isfile functionality."""
    # Mock file properties

    mock_props = create_mock_properties('test', is_folder=False)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    result = azure_storage.isfile('/test.txt')
    assert result is True


def test_stat(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test stat functionality."""
    # Mock file properties
    mock_props = {
        'name': 'test.txt',
        'last_modified': '2023-01-01T00:00:00Z',
        'creation_time': '2023-01-01T00:00:00Z',
    }
    mock_props_obj = MagicMock()
    mock_props_obj.get.return_value = {'hdi_isfolder': False}

    # Override the props object to return our mock data when used as dict
    def mock_props_dict() -> Any:
        return mock_props

    mock_props_obj.__iter__ = lambda: iter(mock_props)
    mock_props_obj.items = lambda: mock_props.items()

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props_obj
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with patch('storix.models.AzureFileProperties.model_validate') as mock_validate:
        mock_file_props = MagicMock()
        mock_validate.return_value = mock_file_props

        result = azure_storage.stat('/test.txt')
        assert result == mock_file_props


def test_tree(azure_storage: Storage, mock_azure_clients: Any) -> None:
    """Test tree functionality."""
    # Mock directory exists
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock recursive get_paths
    mock_path1 = MagicMock()
    mock_path1.name = 'file1.txt'
    mock_path2 = MagicMock()
    mock_path2.name = 'dir1/file2.txt'

    mock_azure_clients['filesystem'].get_paths.return_value = [mock_path1, mock_path2]

    result = azure_storage.tree('/test')
    assert len(result) == 2
    assert all(isinstance(p, Path | StorixPath) for p in result)


# Test context manager and cleanup
def test_context_manager(mock_azure_clients: Any) -> None:
    """Test AzureDataLake as context manager."""
    # Mock home directory for __exit__
    mock_props = create_mock_properties('', is_folder=True)
    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with AzureDataLake(
        adlsg2_account_name='test_account', adlsg2_token='test_token'
    ) as storage:
        assert isinstance(storage, AzureDataLake)

    # Should call close methods
    mock_azure_clients['filesystem'].close.assert_called_once()
    mock_azure_clients['service'].close.assert_called_once()


def test_close(azure_storage: AzureDataLake, mock_azure_clients: Any) -> None:
    """Test close method."""
    azure_storage.close()
    mock_azure_clients['filesystem'].close.assert_called_once()
    mock_azure_clients['service'].close.assert_called_once()


# Test error cases and edge conditions
def test_cp_directory_not_implemented(
    azure_storage: Storage, mock_azure_clients: Any
) -> None:
    """Test cp for directories raises NotImplementedError."""
    # Mock directory properties

    mock_props = create_mock_properties('test', is_folder=True)

    mock_file_client = MagicMock()
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    with pytest.raises(NotImplementedError):
        azure_storage.cp('/sourcedir', '/destdir')


# Integration-style tests (still mocked but more complete workflows)
def test_create_file_and_read_workflow(
    azure_storage: Storage, mock_azure_clients: Any
) -> None:
    """Test complete workflow: create file, write data, read data."""
    mock_file_client = MagicMock()
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock file properties for isfile check
    mock_props = create_mock_properties('test.txt', is_folder=False)
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    # Mock download
    test_data = b'Hello Azure!'
    mock_download = MagicMock()
    mock_download.readall.return_value = test_data
    mock_file_client.download_file.return_value = mock_download

    # Create file with data
    result = azure_storage.touch('/test.txt', test_data)
    assert result is True

    # Read file data
    content = azure_storage.cat('/test.txt')
    assert content == test_data


def test_directory_operations_workflow(
    azure_storage: Storage, mock_azure_clients: Any
) -> None:
    """Test complete directory workflow: create, list, remove."""
    mock_file_client = MagicMock()
    mock_dir_client = MagicMock()

    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client
    mock_azure_clients[
        'filesystem'
    ].get_directory_client.return_value.__enter__.return_value = mock_dir_client
    mock_azure_clients['filesystem'].create_directory.return_value = None

    # Create directory
    azure_storage.mkdir('/testdir')
    mock_azure_clients['filesystem'].create_directory.assert_called_with('/testdir')

    # Mock directory properties for rmdir
    mock_props = create_mock_properties('testdir', is_folder=True)
    mock_file_client.get_file_properties.return_value = mock_props
    mock_file_client.exists.return_value = True

    # Mock empty directory for listing
    mock_azure_clients['filesystem'].get_paths.return_value = []

    # Remove directory
    result = azure_storage.rmdir('/testdir')
    assert result is True
    mock_dir_client.delete_directory.assert_called_once()


# Test sandboxed mode
def test_sandboxed_initialization(mock_azure_clients: Any) -> None:
    """Test sandboxed initialization."""
    storage = AzureDataLake(
        initialpath='/sandbox',
        adlsg2_account_name='test_account',
        adlsg2_token='test_token',
        sandboxed=True,
    )
    assert isinstance(storage, AzureDataLake)


# Performance/edge case tests
def test_large_directory_listing(
    azure_storage: Storage, mock_azure_clients: Any
) -> None:
    """Test listing directory with many files."""
    mock_file_client = MagicMock()
    mock_file_client.exists.return_value = True
    mock_azure_clients[
        'filesystem'
    ].get_file_client.return_value.__enter__.return_value = mock_file_client

    # Mock large number of files
    mock_paths = []
    for i in range(1000):
        mock_path = MagicMock()
        mock_path.name = f'file_{i}.txt'
        mock_paths.append(mock_path)

    mock_azure_clients['filesystem'].get_paths.return_value = mock_paths

    result = azure_storage.ls('/large_dir')
    assert len(result) == 1000


# Skip tests that require real Azure credentials
@pytest.mark.skipif(
    not all(
        [
            os.getenv('ADLSG2_ACCOUNT_NAME'),
            os.getenv('ADLSG2_TOKEN'),
            os.getenv('ADLSG2_CONTAINER_NAME'),
        ]
    ),
    reason='Azure credentials not available',
)
class TestAzureIntegration:
    """Integration tests that require real Azure credentials."""

    @pytest.fixture
    def real_azure_storage(self) -> Storage:
        """Create real AzureDataLake instance with environment credentials."""
        return AzureDataLake(
            container_name=os.getenv('ADLSG2_CONTAINER_NAME') or 'test',
            adlsg2_account_name=os.getenv('ADLSG2_ACCOUNT_NAME'),
            adlsg2_token=os.getenv('ADLSG2_TOKEN'),
            sandboxed=True,  # Use sandbox for safety
        )

    def test_real_azure_connection(self, real_azure_storage: Storage) -> None:
        """Test real connection to Azure."""
        # Simple test to verify connection works
        current_path = real_azure_storage.pwd()
        assert isinstance(current_path, Path)

    def test_real_file_operations(self, real_azure_storage: Storage) -> None:
        """Test real file operations on Azure."""
        test_file = '/test_integration.txt'
        test_content = b'Integration test content'

        try:
            # Create file
            result = real_azure_storage.touch(test_file, test_content)
            assert result is True

            # Check file exists
            assert real_azure_storage.exists(test_file)
            assert real_azure_storage.isfile(test_file)

            # Read content
            content = real_azure_storage.cat(test_file)
            assert content == test_content

        finally:
            # Cleanup
            with contextlib.suppress(Exception):
                real_azure_storage.rm(test_file)
