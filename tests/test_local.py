from pathlib import Path

import pytest

from pytest import MonkeyPatch

from storix import LocalFilesystem, Storage
from storix.types import StorixPath


@pytest.fixture
def storage() -> Storage:
    return LocalFilesystem(sandboxed=False)


@pytest.fixture
def sandboxed_storage(tmp_path: Path) -> Storage:
    return LocalFilesystem(tmp_path, sandboxed=True)


def test_cd(storage: Storage, tmp_path: Path):
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)
    assert storage.pwd() == tmp_path


def test_cd_to_home(storage: Storage):
    """Test cd with None goes to home directory"""
    original_home = storage.home
    storage.cd(None)
    assert storage.pwd() == original_home


def test_cd_nonexistent_path(storage: Storage, tmp_path: Path):
    """Test cd to nonexistent path raises error"""
    nonexistent = tmp_path / 'nonexistent'
    with pytest.raises(ValueError, match='path .* does not exist'):
        storage.cd(nonexistent)


def test_ls(storage: Storage, tmp_path: Path):
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)

    tmp_ls_abs = list(tmp_path.iterdir())
    assert storage.ls(abs=True) == tmp_ls_abs

    tmp_ls = [x.name for x in tmp_ls_abs]
    assert storage.ls() == tmp_ls


def test_ls_with_path(storage: Storage, tmp_path: Path):
    """Test ls with explicit path parameter"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    # Test absolute paths
    abs_result = storage.ls(tmp_path, abs=True)
    assert len(abs_result) == 1
    assert abs_result[0].name == 'test_file.txt'

    # Test relative names
    rel_result = storage.ls(tmp_path, abs=False)
    assert rel_result == ['test_file.txt']


def test_ls_nonexistent_path(storage: Storage, tmp_path: Path):
    """Test ls on nonexistent path raises error"""
    nonexistent = tmp_path / 'nonexistent'
    with pytest.raises(ValueError, match='path .* does not exist'):
        storage.ls(nonexistent)


def test_touch(storage: Storage, tmp_path: Path):
    tmp_path.mkdir(exist_ok=True)

    test_file = 'test_file.txt'

    storage.cd(tmp_path)
    storage.touch(test_file)

    assert (tmp_path / test_file).exists()


def test_touch_with_data(storage: Storage, tmp_path: Path):
    tmp_path.mkdir(exist_ok=True)
    test_file = 'test_file.txt'
    test_data = 'hello world'

    storage.cd(tmp_path)
    assert storage.touch(test_file, test_data)

    assert (tmp_path / test_file).read_bytes().decode() == test_data


def test_touch_with_bytes_data(storage: Storage, tmp_path: Path):
    """Test touch with bytes data"""
    tmp_path.mkdir(exist_ok=True)
    test_file = 'test_file.txt'
    test_data = b'hello world bytes'

    storage.cd(tmp_path)
    assert storage.touch(test_file, test_data)

    assert (tmp_path / test_file).read_bytes() == test_data


def test_touch_nonexistent_parent(storage: Storage, tmp_path: Path):
    """Test touch fails when parent directory doesn't exist"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    result = storage.touch('nonexistent/file.txt')
    assert result is False


def test_exists(storage: Storage, tmp_path: Path):
    """Test exists method"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)
    assert storage.exists('test_file.txt')
    assert not storage.exists('nonexistent.txt')


def test_isdir_isfile(storage: Storage, tmp_path: Path):
    """Test isdir and isfile methods"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()
    subdir = tmp_path / 'subdir'
    subdir.mkdir()

    storage.cd(tmp_path)
    assert storage.isfile('test_file.txt')
    assert not storage.isdir('test_file.txt')
    assert storage.isdir('subdir')
    assert not storage.isfile('subdir')


def test_mkdir(storage: Storage, tmp_path: Path):
    """Test mkdir method"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    storage.mkdir('new_dir')
    assert (tmp_path / 'new_dir').is_dir()


def test_mkdir_with_parents(storage: Storage, tmp_path: Path):
    """Test mkdir creates nested directories"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    # Create parent directory first since protocol doesn't support parents parameter
    storage.mkdir('parent')
    storage.mkdir('parent/child')
    assert (tmp_path / 'parent' / 'child').is_dir()


def test_cat(storage: Storage, tmp_path: Path):
    """Test cat method"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    test_content = b'Hello, World!'
    file.write_bytes(test_content)

    storage.cd(tmp_path)
    result = storage.cat('test_file.txt')
    assert result == test_content


def test_cat_nonexistent(storage: Storage, tmp_path: Path):
    """Test cat on nonexistent file raises error"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    with pytest.raises(ValueError, match='path .* does not exist'):
        storage.cat('nonexistent.txt')


def test_rm(storage: Storage, tmp_path: Path):
    """Test rm method"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)
    assert storage.rm('test_file.txt')
    assert not file.exists()


def test_rm_directory_fails(storage: Storage, tmp_path: Path):
    """Test rm on directory fails"""
    tmp_path.mkdir(exist_ok=True)
    subdir = tmp_path / 'subdir'
    subdir.mkdir()

    storage.cd(tmp_path)
    assert not storage.rm('subdir')


def test_rm_nonexistent(storage: Storage, tmp_path: Path):
    """Test rm on nonexistent file returns False"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    assert not storage.rm('nonexistent.txt')


def test_rmdir(storage: Storage, tmp_path: Path):
    """Test rmdir method"""
    tmp_path.mkdir(exist_ok=True)
    subdir = tmp_path / 'subdir'
    subdir.mkdir()

    storage.cd(tmp_path)
    assert storage.rmdir('subdir')
    assert not subdir.exists()


def test_rmdir_recursive(storage: Storage, tmp_path: Path):
    """Test rmdir with recursive=True"""
    tmp_path.mkdir(exist_ok=True)
    subdir = tmp_path / 'subdir'
    subdir.mkdir()
    (subdir / 'file.txt').touch()
    (subdir / 'nested').mkdir()

    storage.cd(tmp_path)
    assert storage.rmdir('subdir', recursive=True)
    assert not subdir.exists()


def test_rmdir_nonexistent(storage: Storage, tmp_path: Path):
    """Test rmdir on nonexistent directory returns False"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    assert not storage.rmdir('nonexistent')


def test_rmdir_not_directory(storage: Storage, tmp_path: Path):
    """Test rmdir on file returns False"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)
    assert not storage.rmdir('test_file.txt')


def test_mv(storage: Storage, tmp_path: Path):
    """Test mv method"""
    tmp_path.mkdir(exist_ok=True)
    source = tmp_path / 'source.txt'
    source.write_text('test content')
    destination = tmp_path / 'destination.txt'

    storage.cd(tmp_path)
    storage.mv('source.txt', 'destination.txt')

    assert not source.exists()
    assert destination.exists()
    assert destination.read_text() == 'test content'


def test_mv_nonexistent_source(storage: Storage, tmp_path: Path):
    """Test mv with nonexistent source raises error"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    with pytest.raises(ValueError, match='path .* does not exist'):
        storage.mv('nonexistent.txt', 'destination.txt')


def test_cp_file(storage: Storage, tmp_path: Path):
    """Test cp method with file"""
    tmp_path.mkdir(exist_ok=True)
    source = tmp_path / 'source.txt'
    source.write_text('test content')
    destination = tmp_path / 'destination.txt'

    storage.cd(tmp_path)
    storage.cp('source.txt', 'destination.txt')

    assert source.exists()
    assert destination.exists()
    assert destination.read_text() == 'test content'


def test_cp_directory(storage: Storage, tmp_path: Path):
    """Test cp method with directory"""
    tmp_path.mkdir(exist_ok=True)
    source_dir = tmp_path / 'source_dir'
    source_dir.mkdir()
    (source_dir / 'file.txt').write_text('test content')
    destination_dir = tmp_path / 'destination_dir'

    storage.cd(tmp_path)
    storage.cp('source_dir', 'destination_dir')

    assert source_dir.exists()
    assert destination_dir.exists()
    assert (destination_dir / 'file.txt').read_text() == 'test content'


def test_root_property(storage: Storage):
    """Test root property returns /"""
    assert storage.root == Path('/')


def test_pwd(storage: Storage):
    """Test pwd returns current path"""
    current = storage.pwd()
    assert isinstance(current, StorixPath)


# Test initialization scenarios
def test_init_with_tilde(tmp_path: Path):
    """Test initialization with tilde path"""
    # This will expand ~ to home directory
    storage = LocalFilesystem('~/test_dir', sandboxed=False)
    assert isinstance(storage.pwd(), StorixPath)


def test_init_creates_directory(tmp_path: Path):
    """Test initialization creates directory if it doesn't exist"""
    new_dir = tmp_path / 'new_storage_dir'
    assert not new_dir.exists()

    LocalFilesystem(new_dir, sandboxed=False)
    assert new_dir.exists()


def test_init_absolute_path(tmp_path: Path):
    """Test initialization with absolute path"""
    storage = LocalFilesystem(tmp_path, sandboxed=False)
    assert storage.pwd() == tmp_path


def test_init_relative_path():
    """Test initialization with relative path"""
    storage = LocalFilesystem('.', sandboxed=False)
    assert isinstance(storage.pwd(), StorixPath)


def test_sandboxed_initialization(tmp_path: Path):
    """Test sandboxed initialization"""
    storage = LocalFilesystem(tmp_path, sandboxed=True)
    assert isinstance(storage, LocalFilesystem)


# Test NotImplementedError methods
@pytest.mark.skip(reason='WIP')
def test_tree_not_implemented(storage: Storage):
    """Test tree method raises NotImplementedError"""
    with pytest.raises(NotImplementedError):
        storage.tree()


def test_stat_not_implemented(storage: Storage):
    """Test stat method raises NotImplementedError"""
    with pytest.raises(NotImplementedError):
        storage.stat('.')


def test_du_not_implemented(storage: Storage):
    """Test du method raises NotImplementedError"""
    with pytest.raises(NotImplementedError):
        storage.du()


# Test context manager
def test_context_manager(tmp_path: Path):
    """Test LocalFilesystem as context manager"""
    with LocalFilesystem(tmp_path, sandboxed=False) as storage:
        assert isinstance(storage, LocalFilesystem)
        assert storage.pwd() == tmp_path


# Test error handling edge cases
def test_touch_write_error(
    storage: Storage, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test touch handles write errors gracefully"""
    tmp_path.mkdir(exist_ok=True)
    storage.cd(tmp_path)

    # Mock Path.open to raise an exception
    def mock_open(*args: object, **kwargs: object) -> None:
        msg = 'Mock permission error'
        raise PermissionError(msg)

    monkeypatch.setattr('pathlib.Path.open', mock_open)

    result = storage.touch('test_file.txt', 'data')
    assert result is False


def test_rmdir_with_exception(
    storage: Storage, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test rmdir handles exceptions gracefully"""
    tmp_path.mkdir(exist_ok=True)
    subdir = tmp_path / 'subdir'
    subdir.mkdir()

    storage.cd(tmp_path)

    # Mock rmdir to raise an exception
    def mock_rmdir() -> None:
        msg = 'Mock permission error'
        raise PermissionError(msg)

    monkeypatch.setattr('pathlib.Path.rmdir', mock_rmdir)

    result = storage.rmdir('subdir')
    assert result is False


def test_rm_permission_error(
    storage: Storage, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test rm handles permission errors"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)

    # Mock os.remove to raise PermissionError
    def mock_remove(path: str) -> None:
        msg = 'Mock permission error'
        raise PermissionError(msg)

    monkeypatch.setattr('os.remove', mock_remove)

    result = storage.rm('test_file.txt')
    assert result is False


def test_rm_general_exception(
    storage: Storage, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test rm handles general exceptions"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)

    # Mock os.remove to raise a general exception
    def mock_remove(path: str) -> None:
        msg = 'Mock runtime error'
        raise RuntimeError(msg)

    monkeypatch.setattr('os.remove', mock_remove)

    result = storage.rm('test_file.txt')
    assert result is False


def test_rm_file_not_found_error(
    storage: Storage, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test rm handles FileNotFoundError specifically"""
    tmp_path.mkdir(exist_ok=True)
    file = tmp_path / 'test_file.txt'
    file.touch()

    storage.cd(tmp_path)

    # Mock os.remove to raise FileNotFoundError
    def mock_remove(path: str) -> None:
        msg = 'Mock file not found error'
        raise FileNotFoundError(msg)

    monkeypatch.setattr('os.remove', mock_remove)

    result = storage.rm('test_file.txt')
    assert result is False
