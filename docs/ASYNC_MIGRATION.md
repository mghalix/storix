# Seamless Sync to Async Transition

This demonstrates how to seamlessly transition from `storix` to `storix.aio` with minimal code changes.

## Usage Examples

### Sync Version

```python
from storix import LocalFilesystem

# Initialize
storage = LocalFilesystem("/path/to/storage")

# File operations
storage.touch("file.txt", "Hello, World!")
content = storage.cat("file.txt")
exists = storage.exists("file.txt")
print(f"Exists: {exists}")
```

### Async Version

```python
import asyncio
from storix.aio import LocalFilesystem

async def main():
    storage = LocalFilesystem("/path/to/storage")

    await storage.touch("file.txt", "Hello, World!")
    content = await storage.cat("file.txt")
    exists = await storage.exists("file.txt")
    print(f"Exists: {exists}")

if __name__ == "__main__":
    asyncio.run(main())
```

## What Changed?

1. **Import**: `from storix import LocalFilesystem` → `from storix.aio import LocalFilesystem`
2. **Methods**: Add `await` before method calls
3. **Function**: Make your function `async def` and run with `asyncio.run()`

## Identical APIs

Both sync and async versions have **exactly the same**:

-   Constructor parameters
-   Method signatures
-   Return types
-   Error handling
-   Path handling logic

## Available Providers

-   `LocalFilesystem` - Local file system operations
-   `AzureDataLake` - Azure Data Lake Storage Gen2 (async version has stubs)

## Benefits of Async Version

-   **Non-blocking I/O**: File operations don't block the event loop
-   **Concurrent operations**: Multiple file operations can run simultaneously
-   **Better for web apps**: Ideal for async web frameworks like FastAPI, aiohttp
-   **Scalability**: Better resource utilization in I/O-bound applications

## Performance

The async version uses `aiofiles` library which provides:

-   Efficient async file operations
-   Thread pool execution for I/O
-   Async context managers
-   Compatible with all async frameworks

## Migration Strategy

1. **Start small**: Convert one module at a time
2. **Test thoroughly**: Run both versions in parallel initially
3. **Gradual rollout**: Use async version for new features first
4. **Monitor**: Check performance improvements in your specific use case

## Example Applications

-   **Web scraping**: Download files while making HTTP requests
-   **Data processing**: Read/write files while processing data streams
-   **Microservices**: Handle file operations without blocking request processing
-   **Batch jobs**: Process multiple files concurrently
