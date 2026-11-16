import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Load storage code with isolated AstrBot paths and real SQLite storage.

    Args:
        tmp_path: Temporary AstrBot data root.
        monkeypatch: Fixture restoring imported modules after each test.

    Returns:
        Storage modules and the isolated data directory.
    """
    package = "meme_storage_test"
    for suffix in (
        "",
        ".backend",
        ".backend.core",
        ".backend.db",
        ".image_host",
        ".image_host.core",
        ".image_host.interfaces",
    ):
        module = ModuleType(package + suffix)
        module.__path__ = [str(PLUGIN_ROOT / suffix.lstrip(".").replace(".", "/"))]
        monkeypatch.setitem(sys.modules, module.__name__, module)

    path_module = ModuleType("astrbot.core.utils.astrbot_path")
    path_module.get_astrbot_plugin_data_path = lambda: str(tmp_path / "plugin_data")
    monkeypatch.setitem(sys.modules, path_module.__name__, path_module)
    helpers = ModuleType(package + ".backend.core.helpers")
    helpers.MEME_SEND_MODE_STICKER = "sticker"
    helpers.MEME_SEND_MODE_VALUES = ("sticker", "image")
    monkeypatch.setitem(sys.modules, helpers.__name__, helpers)

    def load(suffix, filename):
        name = package + suffix
        spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    legacy = tmp_path / "memes_data" / "memes" / "happy"
    legacy.mkdir(parents=True)
    (legacy / "legacy.png").write_bytes(b"old image")
    config = load(".config", "config.py")
    load(".utils", "utils.py")
    database = load(".backend.db.database", "backend/db/database.py")
    initializer = load(".init", "init.py")
    categories = load(
        ".backend.core.category_manager", "backend/core/category_manager.py"
    )
    files = load(".image_host.core.file_handler", "image_host/core/file_handler.py")
    sync = load(".image_host.core.sync_manager", "image_host/core/sync_manager.py")
    return SimpleNamespace(
        config=config,
        database=database,
        initializer=initializer,
        categories=categories,
        files=files,
        sync=sync,
        data_dir=tmp_path,
    )


def test_initialization_leaves_pre_v4_data_untouched(storage):
    config = storage.config
    nested = config.MEMES_DIR / "happy" / "nested.png"
    nested.parent.mkdir()
    nested.write_bytes(b"unmigrated image")

    assert storage.initializer.init_plugin()

    with storage.database.get_db_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM memes").fetchone()[0] == 0
    assert not (config.MEMES_DIR / "legacy.png").exists()
    assert not (config.MEMES_DIR / "nested.png").exists()
    assert nested.read_bytes() == b"unmigrated image"
    assert (
        storage.data_dir / "memes_data/memes/happy/legacy.png"
    ).read_bytes() == b"old image"
    assert not (config.PLUGIN_DATA_DIR / ".db_migrated").exists()
    assert not (config.PLUGIN_DATA_DIR / ".default_memes_initialized").exists()


def test_v4_database_rows_are_preserved_during_supported_upgrades(storage):
    image = storage.config.MEMES_DIR / "v4.png"
    image.write_bytes(b"v4 image")
    with storage.database.get_db_conn() as conn:
        conn.execute(
            "CREATE TABLE memes (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT UNIQUE, emotions TEXT, personas TEXT, original_hash TEXT)"
        )
        conn.execute(
            "INSERT INTO memes (filename, emotions, personas) VALUES ('v4.png', 'happy', 'alice')"
        )

    assert storage.initializer.init_plugin()
    assert storage.initializer.init_plugin()

    with storage.database.get_db_conn() as conn:
        row = conn.execute("SELECT * FROM memes").fetchone()
    assert row["filename"] == "v4.png"
    assert row["emotions"] == "happy"
    assert row["personas"] == "alice"
    assert row["original_hash"] == hashlib.sha256(image.read_bytes()).hexdigest()
    assert row["send_mode"] == "sticker"


def test_v4_category_description_upgrade_is_still_supported(storage):
    path = storage.config.MEMES_DATA_PATH
    path.write_text(json.dumps({"happy": "Happy memes"}))

    manager = storage.categories.CategoryManager()

    assert manager.get_categories() == ["happy"]
    assert json.loads(path.read_text()) == ["happy"]


def test_cloud_sync_only_processes_flat_images(storage):
    memes = storage.config.MEMES_DIR
    (memes / "root.png").write_bytes(b"image")
    nested = memes / "happy" / "nested.png"
    nested.parent.mkdir()
    nested.write_bytes(b"legacy image")
    host = SimpleNamespace(
        config={"provider": "cloudflare_r2"},
        get_image_list=Mock(
            return_value=[
                {
                    "id": "memes/root.png",
                    "filename": "root.png",
                    "category": "",
                    "size": 5,
                },
                {
                    "id": "memes/happy/nested.png",
                    "filename": "nested.png",
                    "category": "happy",
                    "size": 12,
                },
            ]
        ),
        download_image=Mock(),
    )
    sync = storage.sync.SyncManager(host, memes)

    status = sync.check_sync_status()

    assert status["is_synced"]
    assert status["remote_image_count"] == 1
    assert sync.sync_from_remote()
    host.download_image.assert_not_called()
    assert nested.read_bytes() == b"legacy image"
    assert sync.file_handler.get_file_path("", "root.png") == memes / "root.png"
    with pytest.raises(ValueError, match="flat"):
        sync.file_handler.get_file_path("happy", "nested.png")
