import asyncio
import inspect
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from storix.aio import AzureDataLake as AsyncAzureDataLake
from storix.aio import LocalFilesystem as AsyncLocalFilesystem


class TestAsyncProviderCompatibility:
    """Test compatibility and consistency between sync and async providers."""

    @pytest_asyncio.fixture
    async def fs_pair(self) -> AsyncGenerator[Any, None]:
        """Create both sync and async filesystems for comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from storix.providers.local import (
                LocalFilesystem as SyncLocalFilesystem,
            )

            sync_fs = SyncLocalFilesystem(Path(tmpdir) / "sync", sandboxed=False)
            async_fs = AsyncLocalFilesystem(Path(tmpdir) / "async", sandboxed=False)

            yield {"sync": sync_fs, "async": async_fs}

    @pytest.mark.asyncio
    async def test_api_compatibility(self, fs_pair: Any) -> None:
        """Test that sync and async APIs are identical except for await."""
        sync_fs = fs_pair["sync"]
        async_fs = fs_pair["async"]

        # Test identical file operations
        sync_fs.touch("test.txt", "sync content")
        await async_fs.touch("test.txt", "async content")

        sync_content = sync_fs.cat("test.txt").decode()
        async_content = (await async_fs.cat("test.txt")).decode()

        assert sync_content == "sync content"
        assert async_content == "async content"

        # Test identical directory operations
        sync_fs.mkdir("testdir")
        await async_fs.mkdir("testdir")

        assert sync_fs.exists("testdir") is True
        assert await async_fs.exists("testdir") is True

    @pytest.mark.asyncio
    async def test_method_signatures_match(self) -> None:
        """Test that method signatures are consistent between sync and async."""
        # Get all callable attributes (methods and functions) for async
        async_methods = {
            name: method
            for name, method in inspect.getmembers(AsyncLocalFilesystem, callable)
            if not name.startswith("_")
        }

        # Check that async has corresponding methods
        async_method_names = set(async_methods.keys())

        # Some methods might be properties or have different implementations
        # But core file operations should match
        core_methods = {
            "touch",
            "cat",
            "mkdir",
            "rmdir",
            "rm",
            "mv",
            "cp",
            "exists",
            "isfile",
            "isdir",
            "ls",
            "cd",
        }

        missing_async = core_methods - async_method_names
        assert len(missing_async) == 0, f"Missing async methods: {missing_async}"


@pytest.mark.integration
class TestAsyncProviderIntegration:
    """Integration tests for async providers."""

    @pytest.mark.asyncio
    async def test_complex_async_workflow(self) -> None:
        """Test a complex workflow using async providers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = AsyncLocalFilesystem(tmpdir, sandboxed=False)

            # Create project structure
            await fs.mkdir("project")
            await fs.cd("project")

            # Create main files
            await fs.touch("README.md", "# Async Project\n\nThis is an async project.")
            await fs.touch(
                "main.py",
                "import asyncio\n\nasync def main():\n    print('Hello, async!')",
            )

            # Create source directory
            await fs.mkdir("src")
            await fs.touch("src/__init__.py", "")
            await fs.touch(
                "src/module.py",
                "async def hello():\n    return 'Hello from async module!'",
            )

            # Create tests directory
            await fs.mkdir("tests")
            await fs.touch(
                "tests/test_module.py",
                "import pytest\n\n@pytest.mark.asyncio\nasync def test_hello(self, *args: Any: Any) -> None:\n    assert True",
            )

            # Verify structure
            files = await fs.ls(".")  # Use current directory instead of absolute path
            expected_files = ["README.md", "main.py", "src", "tests"]
            assert all(f in files for f in expected_files)

            # Test nested navigation
            await fs.cd("src")
            src_files = await fs.ls(".")
            assert "__init__.py" in src_files
            assert "module.py" in src_files

            # Read and verify file contents
            await fs.cd("/")  # Go to root instead of absolute project path
            await fs.cd("project")
            readme_content = await fs.cat("README.md")
            assert b"Async Project" in readme_content

            module_content = await fs.cat("src/module.py")
            assert b"async def hello" in module_content

    @pytest.mark.asyncio
    async def test_async_provider_import_compatibility(self) -> None:
        """Test that async providers can be imported and used as expected."""
        # Test direct import
        from storix.aio.providers import AzureDataLake, LocalFilesystem

        # Test that they're the async versions
        assert LocalFilesystem is AsyncLocalFilesystem
        assert AzureDataLake is AsyncAzureDataLake

        # Test instantiation
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = LocalFilesystem(tmpdir, sandboxed=False)
            assert fs is not None

            # Test async operations work
            await fs.touch("import_test.txt", "import test")
            assert await fs.exists("import_test.txt") is True

    @pytest.mark.asyncio
    async def test_async_provider_performance_comparison(self) -> None:
        """Compare async vs sync provider performance for educational purposes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import time

            from storix.providers.local import (
                LocalFilesystem as SyncLocalFilesystem,
            )

            sync_fs = SyncLocalFilesystem(Path(tmpdir) / "sync", sandboxed=False)
            async_fs = AsyncLocalFilesystem(Path(tmpdir) / "async", sandboxed=False)

            # Test sync performance
            start_time = time.time()
            for i in range(10):
                sync_fs.touch(f"sync_file_{i}.txt", f"sync content {i}")
            sync_time = time.time() - start_time

            # Test async performance (sequential)
            start_time = time.time()
            for i in range(10):
                await async_fs.touch(f"async_seq_file_{i}.txt", f"async content {i}")
            async_seq_time = time.time() - start_time

            # Test async performance (concurrent)
            start_time = time.time()
            tasks = []
            for i in range(10):
                tasks.append(
                    async_fs.touch(f"async_conc_file_{i}.txt", f"async content {i}")
                )
            await asyncio.gather(*tasks)
            async_conc_time = time.time() - start_time

            # Verify all files were created
            sync_files = sync_fs.ls(".")  # Use current directory
            async_seq_files = await async_fs.ls(".")  # Use current directory

            assert len(sync_files) == 10  # 10 sync files
            assert len(async_seq_files) == 20  # 10 async_seq + 10 async_conc files

            # Note: We don't assert on timing as it can be variable,
            # but typically concurrent async should be fastest
            print(f"Sync time: {sync_time:.4f}s")
            print(f"Async sequential time: {async_seq_time:.4f}s")
            print(f"Async concurrent time: {async_conc_time:.4f}s")
