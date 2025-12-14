import asyncio
import tempfile

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

from storix import StorixPath
from storix.aio import LocalFilesystem as AsyncLocalFilesystem
from storix.sandbox import SandboxedPathHandler


class TestAsyncLocalFilesystem:
    """Comprehensive tests for the async LocalFilesystem provider."""

    @pytest.fixture
    async def async_fs(self) -> AsyncGenerator[Any]:
        """Create an async local filesystem for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = AsyncLocalFilesystem(tmpdir, sandboxed=False)
            yield fs

    @pytest.fixture
    async def async_fs_with_data(self) -> AsyncGenerator[Any]:
        """Create an async filesystem with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create test structure
            test_file = tmpdir_path / 'test.txt'
            test_file.write_text('Hello, async world!')

            test_dir = tmpdir_path / 'testdir'
            test_dir.mkdir()

            nested_file = test_dir / 'nested.txt'
            nested_file.write_text('Nested content')

            fs = AsyncLocalFilesystem(tmpdir, sandboxed=False)
            yield {
                'fs': fs,
                'tmpdir': tmpdir_path,
                'test_file': test_file,
                'test_dir': test_dir,
                'nested_file': nested_file,
            }

    async def test_async_basic_properties(self, async_fs: Any) -> None:
        """Test basic properties of async filesystem."""
        assert async_fs.root == Path('/')
        # async_fs.home should be the temp directory path, not "/"
        assert async_fs.home.is_absolute()  # Just check it's absolute
        assert async_fs.pwd().is_absolute()  # Just check it's absolute

    async def test_async_touch_and_cat(self, async_fs: Any) -> None:
        """Test async file creation and reading."""
        # Create file with string data
        result = await async_fs.touch('test.txt', 'async test content')
        assert result is True

        # Read file content
        content = await async_fs.cat('test.txt')
        assert content.decode() == 'async test content'

        # Create file with bytes data
        result = await async_fs.touch('test_bytes.txt', b'binary content')
        assert result is True

        content = await async_fs.cat('test_bytes.txt')
        assert content == b'binary content'

    async def test_async_exists_operations(self, async_fs_with_data: Any) -> None:
        """Test async existence checking operations."""
        fs = async_fs_with_data['fs']

        # Test file existence
        assert await fs.exists('test.txt') is True
        assert await fs.exists('nonexistent.txt') is False

        # Test directory existence
        assert await fs.exists('testdir') is True
        assert await fs.exists('nonexistent_dir') is False

        # Test file/directory type checking
        assert await fs.isfile('test.txt') is True
        assert await fs.isfile('testdir') is False
        assert await fs.isdir('testdir') is True
        assert await fs.isdir('test.txt') is False

    async def test_async_directory_operations(self, async_fs: Any) -> None:
        """Test async directory operations."""
        # Create directory
        await async_fs.mkdir('newdir')
        assert await async_fs.exists('newdir') is True
        assert await async_fs.isdir('newdir') is True

        # Create nested directories
        await async_fs.mkdir('parent/child', parents=True)
        assert await async_fs.exists('parent') is True
        assert await async_fs.exists('parent/child') is True

        # List directory contents
        await async_fs.touch('parent/file1.txt', 'content1')
        await async_fs.touch('parent/file2.txt', 'content2')

        contents = await async_fs.ls('parent')
        assert 'child' in contents
        assert 'file1.txt' in contents
        assert 'file2.txt' in contents

        # List with absolute paths
        abs_contents = await async_fs.ls('parent', abs=True)
        print(abs_contents)
        assert all(isinstance(item, StorixPath) for item in abs_contents)

    async def test_async_file_operations(self, async_fs_with_data: Any) -> None:
        """Test async file manipulation operations."""
        fs = async_fs_with_data['fs']

        # Copy file
        await fs.cp('test.txt', 'test_copy.txt')
        assert await fs.exists('test_copy.txt') is True

        copy_content = await fs.cat('test_copy.txt')
        original_content = await fs.cat('test.txt')
        assert copy_content == original_content

        # Move file
        await fs.mv('test_copy.txt', 'test_moved.txt')
        assert await fs.exists('test_copy.txt') is False
        assert await fs.exists('test_moved.txt') is True

        # Remove file
        result = await fs.rm('test_moved.txt')
        assert result is True
        assert await fs.exists('test_moved.txt') is False

    async def test_async_directory_removal(self, async_fs: Any) -> None:
        """Test async directory removal operations."""
        # Create directory with content
        await async_fs.mkdir('remove_test')
        await async_fs.touch('remove_test/file.txt', 'content')
        await async_fs.mkdir('remove_test/subdir')

        # Try to remove non-empty directory (should fail)
        result = await async_fs.rmdir('remove_test')
        assert result is False
        assert await async_fs.exists('remove_test') is True

        # Remove recursively
        result = await async_fs.rmdir('remove_test', recursive=True)
        assert result is True
        assert await async_fs.exists('remove_test') is False

    async def test_async_cd_operations(self, async_fs_with_data: Any) -> None:
        """Test async directory navigation."""
        fs = async_fs_with_data['fs']

        # Change to subdirectory
        await fs.cd('testdir')

        # Touch file in current directory
        await fs.touch('local_file.txt', 'local content')
        assert await fs.exists('local_file.txt') is True

        # Change back to root
        await fs.cd('/')

        # File should exist in the subdirectory
        assert await fs.exists('testdir/local_file.txt') is True

    async def test_async_error_handling(self, async_fs: Any) -> None:
        """Test async error handling."""
        # Try to read non-existent file
        with pytest.raises(ValueError, match='does not exist'):
            await async_fs.cat('nonexistent.txt')

        # Try to change to non-existent directory
        with pytest.raises(ValueError, match='does not exist'):
            await async_fs.cd('nonexistent_dir')

        # Try to remove non-existent file
        result = await async_fs.rm('nonexistent.txt')
        assert result is False

    async def test_async_context_manager(self, async_fs: Any) -> None:
        """Test async filesystem as context manager."""
        async with async_fs:
            await async_fs.touch('context_test.txt', 'context content')
            assert await async_fs.exists('context_test.txt') is True

        # After context, should still work
        assert await async_fs.exists('context_test.txt') is True

    async def test_async_chroot_operation(self, async_fs_with_data: Any) -> None:
        """Test async chroot operation."""
        fs = async_fs_with_data['fs']

        # Create subdirectory and chroot to it
        await fs.mkdir('chroot_test')
        await fs.touch('chroot_test/chroot_file.txt', 'chroot content')

        new_fs = fs.chroot('chroot_test')

        # Should be able to see the file from new root
        assert await new_fs.exists('chroot_file.txt') is True
        content = await new_fs.cat('chroot_file.txt')
        assert content.decode() == 'chroot content'

    async def test_async_with_sandboxing(self) -> None:
        """Test async providers work correctly with sandboxing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox_dir = Path(tmpdir) / 'sandbox'
            sandbox_dir.mkdir()

            # Create sandboxed async filesystem
            fs = AsyncLocalFilesystem(
                sandbox_dir, sandboxed=True, sandbox_handler=SandboxedPathHandler
            )

            # Test basic operations work in sandbox
            await fs.touch('/safe_file.txt', 'safe content')
            assert await fs.exists('/safe_file.txt') is True

            content = await fs.cat('/safe_file.txt')
            assert content.decode() == 'safe content'

            # Test that escapes are blocked
            with pytest.raises(ValueError, match='escape sandbox boundaries'):
                await fs.touch('../escape.txt', 'escaped content')

    async def test_concurrent_operations(self) -> None:
        """Test that async operations can run concurrently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = AsyncLocalFilesystem(tmpdir, sandboxed=False)

            # Create multiple files concurrently
            tasks = []
            for i in range(10):
                tasks.append(fs.touch(f'file_{i}.txt', f'content {i}'))

            results = await asyncio.gather(*tasks)
            assert all(results)  # All operations should succeed

            # Verify all files were created
            for i in range(10):
                assert await fs.exists(f'file_{i}.txt') is True
                content = await fs.cat(f'file_{i}.txt')
                assert content.decode() == f'content {i}'

    async def test_async_directory_listing_performance(self) -> None:
        """Test async directory listing with many files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = AsyncLocalFilesystem(tmpdir, sandboxed=False)

            # Create many files
            tasks = []
            for i in range(100):
                tasks.append(fs.touch(f'perf_file_{i:03d}.txt', f'content {i}'))

            await asyncio.gather(*tasks)

            # List directory - should be fast
            files = await fs.ls('/')
            assert len(files) == 100

            # Verify files are correctly named
            expected_files = [f'perf_file_{i:03d}.txt' for i in range(100)]
            assert sorted(files) == sorted(expected_files)
