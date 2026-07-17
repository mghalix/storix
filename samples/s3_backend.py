"""S3 in one page: sessions, presigned URLs, and zero SDK vocabulary.

`S3Backend` gives the whole storix surface over any S3-compatible
store. This demo runs against a throwaway local MinIO so it needs no
cloud account:

    docker run --rm -d --name minio -p 9000:9000 minio/minio server /data
    docker exec minio mkdir /data/storix-demo   # buckets are directories

Against real S3, drop `endpoint` and let the standard AWS chain supply
credentials; the session code never changes.

Requires the extra:  uv add 'storix[s3]'
Run:  uv run python samples/s3_backend.py
"""

import asyncio

from storix.aio import get_storage


async def main() -> None:
    fs = get_storage(
        's3',
        bucket='storix-demo',
        endpoint='http://localhost:9000',  # drop for real S3
        region='us-east-1',
        access_key_id='minioadmin',
        secret_access_key='minioadmin',
    )

    await fs.mkdir('/reports', parents=True)
    await fs.echo(b'quarterly numbers', '/reports/q1.txt')

    print('ls     ->', await fs.ls('/reports'))
    print('cat    ->', await fs.cat('/reports/q1.txt'))
    print('du     ->', await fs.du('/reports'), 'bytes')

    # a time-limited link, minted locally (no upload, no proxying)
    print('url    ->', await fs.url('/reports/q1.txt', expires_in=600))

    # GCS is the same session with different configuration:
    # fs = get_storage('gcs', bucket='my-bucket',
    #                  credential_path='/path/to/service-account.json')


if __name__ == '__main__':
    asyncio.run(main())
