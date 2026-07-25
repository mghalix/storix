"""Settings parsing: the shared transfer sizes and how they are spelled."""

import pytest

from pydantic import ValidationError

from storix.config import AzureConfig, LocalConfig, S3Config, StorixSettings


@pytest.mark.parametrize(
    ('spelled', 'expected'),
    [
        ('8388608', 8388608),  # a plain byte count still works
        ('8MiB', 8 * 1024 * 1024),  # IEC: a power of two
        ('8MB', 8_000_000),  # SI: a power of ten, and not a synonym
        ('8 MiB', 8 * 1024 * 1024),  # a space is allowed
        ('8mib', 8 * 1024 * 1024),  # case does not matter
        ('512KiB', 512 * 1024),
    ],
)
def test_transfer_sizes_accept_human_readable_spellings(
    monkeypatch, spelled: str, expected: int
):
    """Given a size as text, when settings load, then it resolves to bytes."""
    monkeypatch.setenv('STORIX_AZURE_READ_CHUNK_SIZE', spelled)

    assert AzureConfig().read_chunk_size == expected


def test_every_provider_shares_the_spelling(monkeypatch):
    """Given each provider's variable, when set, then all parse the same way."""
    monkeypatch.setenv('STORIX_S3_WRITE_CHUNK_SIZE', '2MiB')
    monkeypatch.setenv('STORIX_LOCAL_READ_CHUNK_SIZE', '512KiB')

    assert S3Config().write_chunk_size == 2 * 1024 * 1024
    assert LocalConfig().read_chunk_size == 512 * 1024


def test_a_nonsense_size_is_rejected_by_name(monkeypatch):
    """Given an unreadable size, when settings load, then it says so."""
    monkeypatch.setenv('STORIX_AZURE_READ_CHUNK_SIZE', '8 potatoes')

    with pytest.raises(ValidationError, match='byte unit'):
        AzureConfig()


def test_a_non_positive_size_is_rejected(monkeypatch):
    """Given zero, when settings load, then the positive bound still holds."""
    monkeypatch.setenv('STORIX_AZURE_WRITE_CHUNK_SIZE', '0')

    with pytest.raises(ValidationError, match='greater than 0'):
        AzureConfig()


def test_transfer_ranges_stays_a_count(monkeypatch):
    """Given a range ceiling, when settings load, then it is a plain count."""
    monkeypatch.setenv('STORIX_MAX_TRANSFER_RANGES', '4')

    assert StorixSettings().max_transfer_ranges == 4
