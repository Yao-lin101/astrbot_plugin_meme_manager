import base64
import importlib.util
import io
import logging
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from quart import Quart

pytestmark = pytest.mark.asyncio
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def image_api(tmp_path, monkeypatch):
    """Load the image API with isolated plugin data and database dependencies.

    Args:
        tmp_path: Temporary data directory supplied by pytest.
        monkeypatch: Fixture that restores the module registry after the test.

    Returns:
        The loaded API module and a Quart test client.
    """
    package = "meme_image_api_test"
    for suffix in ("", ".backend", ".backend.web", ".backend.web.api"):
        module = ModuleType(package + suffix)
        module.__path__ = [str(PLUGIN_ROOT / suffix.lstrip(".").replace(".", "/"))]
        monkeypatch.setitem(sys.modules, module.__name__, module)

    dependencies = {
        ".config": {"MEMES_DIR": tmp_path / "memes", "PLUGIN_DATA_DIR": tmp_path},
        ".backend.core.helpers": {
            "MEME_SEND_MODE_STICKER": "sticker",
            "normalize_meme_send_mode": None,
        },
        ".backend.db.database": {"get_db_conn": None},
        ".backend.db.models": dict.fromkeys(
            (
                "DuplicateEmojiError",
                "SimilarEmojiError",
                "add_emoji_to_category",
                "delete_emoji_from_category",
                "get_emoji_by_category",
            )
        ),
    }
    for suffix, attributes in dependencies.items():
        module = ModuleType(package + suffix)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, module.__name__, module)

    name = package + ".backend.web.api.emoji"
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_ROOT / "backend/web/api/emoji.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    module.MEMES_DIR.mkdir()
    app = Quart(__name__)
    app.add_url_rule("/image", view_func=module.get_emoji_file_base64)
    return module, app.test_client()


async def test_original_gif_retains_animation_and_special_filename(image_api):
    api, client = image_api
    filename = "表情 & + % #.gif"
    path = api.MEMES_DIR / filename
    frames = [Image.new("RGB", (400, 200), color) for color in ("red", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    response = await client.get("/image", query_string={"filename": filename})
    data = await response.get_json()

    assert response.status_code == 200
    assert data["mime"] == data["content_type"] == "image/gif"
    assert base64.b64decode(data["base64"]) == path.read_bytes()
    with Image.open(io.BytesIO(base64.b64decode(data["base64"]))) as image:
        assert image.n_frames == 2


async def test_thumbnail_is_static_and_reuses_disk_cache(image_api, monkeypatch):
    api, client = image_api
    filename = "animated.gif"
    frames = [Image.new("RGB", (400, 200), color) for color in ("red", "blue")]
    frames[0].save(
        api.MEMES_DIR / filename, save_all=True, append_images=frames[1:], duration=100
    )
    query = {"filename": filename, "thumbnail": "1"}

    response = await client.get("/image", query_string=query)
    data = await response.get_json()
    assert response.status_code == 200
    with Image.open(io.BytesIO(base64.b64decode(data["base64"]))) as image:
        assert image.size == (150, 75)
        assert not getattr(image, "is_animated", False)
        assert Image.MIME[image.format] == data["content_type"]
        red, _, blue = image.convert("RGB").getpixel((0, 0))
        assert red > blue

    def fail_if_opened(*args, **kwargs):
        raise AssertionError("A cached thumbnail must not decode the source again")

    monkeypatch.setattr(api.PILImage, "open", fail_if_opened)
    second = await client.get("/image", query_string=query)
    assert await second.get_json() == data


async def test_modified_source_regenerates_thumbnail(image_api):
    api, client = image_api
    path = api.MEMES_DIR / "image.png"
    query = {"filename": path.name, "thumbnail": "true"}
    Image.new("RGB", (400, 200), "red").save(path)
    first = await client.get("/image", query_string=query)
    first_data = await first.get_json()
    thumb_path = next((api.PLUGIN_DATA_DIR / "thumbnails").iterdir())
    os.utime(thumb_path, ns=(1, 1))
    Image.new("RGB", (200, 400), "blue").save(path)

    second = await client.get("/image", query_string=query)
    second_data = await second.get_json()
    assert first_data["base64"] != second_data["base64"]
    with Image.open(io.BytesIO(base64.b64decode(second_data["base64"]))) as image:
        assert image.size == (75, 150)


async def test_thumbnail_failure_returns_original(image_api, monkeypatch, caplog):
    api, client = image_api
    path = api.MEMES_DIR / "image.png"
    Image.new("RGB", (400, 200), "red").save(path)

    def fail_to_save(*args, **kwargs):
        raise OSError("Thumbnail cache is unavailable")

    monkeypatch.setattr(Image.Image, "save", fail_to_save)
    with caplog.at_level(logging.WARNING):
        response = await client.get(
            "/image", query_string={"filename": path.name, "thumbnail": "1"}
        )
    data = await response.get_json()
    assert response.status_code == 200
    assert data["content_type"] == "image/png"
    assert base64.b64decode(data["base64"]) == path.read_bytes()
    assert "using original image" in caplog.text


async def test_legacy_category_image_is_supported(image_api):
    api, client = image_api
    category = api.MEMES_DIR / "happy"
    category.mkdir()
    Image.new("RGB", (20, 20), "red").save(category / "legacy.png")
    response = await client.get("/image", query_string={"filename": "legacy.png"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "filename",
    ["", "../private.png", "/private.png", "..\\private.png", ".", "..", "bad\x00.png"],
)
async def test_invalid_filename_is_rejected(image_api, filename):
    _, client = image_api
    response = await client.get("/image", query_string={"filename": filename})
    assert response.status_code == 400


async def test_missing_image_and_external_symlink_are_rejected(image_api):
    api, client = image_api
    outside = api.PLUGIN_DATA_DIR / "private.png"
    Image.new("RGB", (20, 20), "red").save(outside)
    (api.MEMES_DIR / "link.png").symlink_to(outside)
    for filename in ("missing.png", "link.png"):
        response = await client.get("/image", query_string={"filename": filename})
        assert response.status_code == 404


async def test_empty_library_returns_not_found(image_api):
    api, client = image_api
    api.MEMES_DIR.rmdir()
    response = await client.get("/image", query_string={"filename": "missing.png"})
    assert response.status_code == 404


async def test_wrapped_image_api_does_not_register_public_routes(
    image_api, monkeypatch
):
    api, _ = image_api
    astrbot = ModuleType("astrbot")
    astrbot.__path__ = []
    astrbot_api = ModuleType("astrbot.api")
    astrbot_api.logger = logging.getLogger("meme_image_api_test")
    monkeypatch.setitem(sys.modules, "astrbot", astrbot)
    monkeypatch.setitem(sys.modules, "astrbot.api", astrbot_api)
    spec = importlib.util.spec_from_file_location(
        "meme_image_api_test.backend.web.api_registrar",
        PLUGIN_ROOT / "backend/web/api_registrar.py",
    )
    registrar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registrar)
    sender = SimpleNamespace(
        img_sync=None, category_manager=None, config={}, context={}
    )
    Image.new("RGB", (20, 20), "red").save(api.MEMES_DIR / "image.png")
    app = Quart(__name__)
    app.add_url_rule(
        "/image",
        view_func=registrar.wrap_api_handler(sender, api.get_emoji_file_base64),
    )
    register_route = Mock(wraps=app.add_url_rule)
    monkeypatch.setattr(app, "add_url_rule", register_route)

    response = await app.test_client().get(
        "/image", query_string={"filename": "image.png", "thumbnail": "1"}
    )
    assert response.status_code == 200
    assert (await response.get_json())["base64"]
    assert app.config["PLUGIN_CONFIG"]["sender"] is sender
    register_route.assert_not_called()
