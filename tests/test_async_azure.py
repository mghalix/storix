from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from storix.aio import AzureDataLake as AsyncAzureDataLake


# Type alias for mock clients
MockAzureClient = dict[str, AsyncMock | MagicMock]


class TestAsyncAzureDataLake:
    """Tests for the async AzureDataLake provider."""

    @pytest.fixture
    async def mock_azure_client(self) -> AsyncGenerator[MockAzureClient]:
        """Create a mock Azure client for testing."""
        with patch(
            'storix.aio.providers.azure.AsyncDataLakeServiceClient'
        ) as mock_client:
            # Mock the service client
            mock_service = AsyncMock()
            mock_client.return_value = mock_service

            # Mock filesystem client - this should NOT be an AsyncMock since it'
            # s not a coroutine
            mock_filesystem = MagicMock()  # Regular mock, not AsyncMock

            # Patch get_file_system_client to be a regular function returning
            # mock_filesystem
            def get_file_system_client(container_name: str) -> MagicMock:
                return mock_filesystem

            mock_service.get_file_system_client = get_file_system_client

            # Patch create_directory to be an AsyncMock
            mock_filesystem.create_directory = AsyncMock()

            # Mock directory and file clients as context managers
            mock_dir_client = AsyncMock()
            mock_file_client = AsyncMock()

            # Patch get_file_properties to return a dict (not an AsyncMock) with valid
            # datetimes
            mock_file_client.get_file_properties = AsyncMock(
                return_value={
                    'name': 'test.txt',
                    'hdi_isfolder': False,
                    'last_modified': datetime.now(tz=UTC),
                    'creation_time': datetime.now(tz=UTC),
                    'metadata': {},
                }
            )

            # Set up context manager behavior
            mock_filesystem.get_directory_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_dir_client
            )
            mock_filesystem.get_directory_client.return_value.__aexit__ = AsyncMock(
                return_value=None
            )
            mock_filesystem.get_file_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_file_client
            )
            mock_filesystem.get_file_client.return_value.__aexit__ = AsyncMock(
                return_value=None
            )
            # Patch get_directory_client and get_file_client to return the correct mock
            # with create_directory
            mock_filesystem.get_directory_client.return_value.create_directory = (
                mock_dir_client.create_directory
            )
            mock_filesystem.get_file_client.return_value.create_directory = (
                mock_file_client.create_directory
            )

            # Use a dictionary to store mocks by path
            dir_mocks = {}
            file_mocks = {}

            def get_directory_client(path: str) -> AsyncMock:
                if path not in dir_mocks:
                    dir_mock = AsyncMock()
                    dir_mock.create_directory = AsyncMock()
                    dir_mock.__aenter__.return_value = dir_mock
                    dir_mock.__aexit__.return_value = None
                    dir_mocks[path] = dir_mock
                # Ensure for '/test/testdir' the create_directory is an AsyncMock and
                # patch filesystem.create_directory
                if path == '/test/testdir':
                    dir_mocks[path].create_directory = AsyncMock()
                    mock_filesystem.create_directory = dir_mocks[path].create_directory
                return dir_mocks[path]

            mock_filesystem.get_directory_client = get_directory_client

            def get_file_client(path: str) -> AsyncMock:
                if path not in file_mocks:
                    file_mock = AsyncMock()
                    file_mock.get_file_properties = mock_file_client.get_file_properties
                    file_mock.download_file = mock_file_client.download_file
                    file_mock.create_directory = mock_file_client.create_directory
                    file_mock.create_file = AsyncMock()
                    file_mock.upload_data = AsyncMock()
                    file_mock.exists = AsyncMock(return_value=True)
                    file_mock.__aenter__.return_value = file_mock
                    file_mock.__aexit__.return_value = None
                    file_mocks[path] = file_mock
                return file_mocks[path]

            mock_filesystem.get_file_client = get_file_client

            # For error handling: patch download_file to raise ResourceNotFoundError
            # for nonexistent.txt
            from azure.core.exceptions import ResourceNotFoundError

            async def download_file_side_effect(*args: Any, **_: Any) -> AsyncMock:
                if args and 'nonexistent.txt' in str(args[0]):
                    msg = 'File not found'
                    raise ResourceNotFoundError(msg)
                return AsyncMock(readall=AsyncMock(return_value=b'test content'))

            mock_file_client.download_file.side_effect = download_file_side_effect

            yield {
                'service': mock_service,
                'filesystem': mock_filesystem,
                'directory': mock_dir_client,
                'file': mock_file_client,
            }

    async def test_async_azure_initialization(self, mock_azure_client: Any) -> None:
        """Test async Azure provider initialization."""
        azure_fs = AsyncAzureDataLake(
            initialpath='/test',
            container_name='testfs',
            adlsg2_account_name='test',
            adlsg2_token='test_key',
        )

        assert azure_fs.root == Path('/')
        assert azure_fs.home == Path('/')

    async def test_async_azure_touch_operation(self, mock_azure_client: Any) -> None:
        """Test async Azure touch operation."""
        azure_fs = AsyncAzureDataLake(
            initialpath='/test',
            container_name='testfs',
            adlsg2_account_name='test',
            adlsg2_token='test_key',
        )
        result = await azure_fs.touch('test.txt', 'test content')
        assert result is True
        file_mock = azure_fs._filesystem.get_file_client('/test/test.txt')
        file_mock.create_file.assert_called_once()
        file_mock.upload_data.assert_called_once()

    async def test_async_azure_cat_operation(self, mock_azure_client: Any) -> None:
        """Test async Azure cat operation."""
        mocks = mock_azure_client

        # Mock file download
        mock_stream = AsyncMock()
        mock_stream.readall.return_value = b'test content'
        mocks['file'].download_file.return_value = mock_stream

        azure_fs = AsyncAzureDataLake(
            initialpath='/test',
            container_name='testfs',
            adlsg2_account_name='test',
            adlsg2_token='test_key',
        )

        content = await azure_fs.cat('test.txt')
        assert content == b'test content'

        mocks['file'].download_file.assert_called_once()

    async def test_async_azure_mkdir_operation(self, mock_azure_client: Any) -> None:
        """Test async Azure mkdir operation."""
        mocks = mock_azure_client

        azure_fs = AsyncAzureDataLake(
            initialpath='/test',
            container_name='testfs',
            adlsg2_account_name='test',
            adlsg2_token='test_key',
        )
        azure_fs._filesystem = mocks['filesystem']

        await azure_fs.mkdir('testdir')

        # Assert create_directory was called on the filesystem mock
        # noqa: SLF001 (accessing protected member for test purposes)
        azure_fs._filesystem.create_directory.assert_called_once_with('/test/testdir')

    async def test_async_azure_exists_operation(self, mock_azure_client: Any) -> None:
        """Test async Azure exists operation."""
        azure_fs = AsyncAzureDataLake(
            initialpath='/test',
            container_name='testfs',
            adlsg2_account_name='test',
            adlsg2_token='test_key',
        )
        result = await azure_fs.exists('test.txt')
        assert result is True
        file_mock = azure_fs._filesystem.get_file_client('/test/test.txt')
        file_mock.exists.assert_called_once()

    async def test_async_azure_error_handling(self, mock_azure_client: Any) -> None:
        """Test async Azure error handling."""
        mocks = mock_azure_client

        from azure.core.exceptions import ResourceNotFoundError

        mocks['file'].download_file.side_effect = ResourceNotFoundError(
            'File not found'
        )

        azure_fs = AsyncAzureDataLake(
            initialpath='/test',
            container_name='testfs',
            adlsg2_account_name='test',
            adlsg2_token='test_key',
        )

        with pytest.raises(ResourceNotFoundError, match='File not found'):
            await azure_fs.cat('nonexistent.txt')
