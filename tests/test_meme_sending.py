import asyncio
import importlib
import importlib.util
import logging
import sqlite3
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image as PILImage

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def meme_plugin(tmp_path, monkeypatch):
    """Load sending and lifecycle code with isolated storage and AstrBot services.

    Args:
        tmp_path: Temporary directory for the library and configuration.
        monkeypatch: Fixture restoring imported modules after each test.

    Returns:
        Plugin module, a sender, its context, and registered hook names.
    """
    package = "meme_sending_test"
    for suffix in (
        "",
        ".backend",
        ".backend.core",
        ".backend.db",
        ".backend.handlers",
        ".image_host",
    ):
        module = ModuleType(package + suffix)
        module.__path__ = [str(PLUGIN_ROOT / suffix.lstrip(".").replace(".", "/"))]
        monkeypatch.setitem(sys.modules, module.__name__, module)

    hooks = []

    def hook(name):
        def factory(*args, **kwargs):
            def decorator(function):
                hooks.append((name, function.__name__))
                function.command = hook("command")
                return function

            return decorator

        return factory

    class Image:
        @classmethod
        def fromFileSystem(cls, path):
            component = cls()
            component.file = str(path)
            return component

    class Star:
        def __init__(self, context):
            self.context = context

    tool = SimpleNamespace(
        name="steal_meme",
        parameters={
            "properties": {
                "image_url": {},
                "categories": {},
                "category": {},
                "description": {},
            }
        },
    )
    tool_manager = SimpleNamespace(func_list=[tool])
    filters = SimpleNamespace(
        **{
            name: hook(name)
            for name in (
                "on_plugin_loaded",
                "command_group",
                "permission_type",
                "event_message_type",
                "on_llm_response",
                "on_decorating_result",
                "after_message_sent",
            )
        }
    )
    filters.PermissionType = SimpleNamespace(ADMIN="admin")
    modules = {
        "astrbot": {},
        "astrbot.api": {"logger": logging.getLogger(package)},
        "astrbot.api.all": {"__all__": ["llm_tool"], "llm_tool": hook("llm_tool")},
        "astrbot.api.event": {"AstrMessageEvent": object, "filter": filters},
        "astrbot.api.event.filter": {
            "EventMessageType": SimpleNamespace(ALL="all", GROUP_MESSAGE="group")
        },
        "astrbot.api.message_components": {"__all__": ["Image"], "Image": Image},
        "astrbot.api.star": {"Context": object, "Star": Star},
        "astrbot.core.message.components": {"Image": Image},
        "astrbot.core.message.message_event_result": {
            "MessageChain": lambda chain: SimpleNamespace(chain=chain)
        },
        "astrbot.core.provider.register": {"llm_tools": tool_manager},
        "astrbot.core.star.star_handler": {"star_handlers_registry": []},
        "astrbot.core.star.star": {"star_registry": []},
        package + ".config": {
            "PLUGIN_DATA_DIR": tmp_path,
            "MEMES_DIR": tmp_path / "memes",
            "MEMES_DATA_PATH": tmp_path / "categories.json",
        },
        package + ".image_host.img_sync": {"ImageSync": Mock()},
        package + ".init": {"init_plugin": lambda: True},
    }
    for name, attributes in modules.items():
        module = ModuleType(name)
        module.__path__ = []
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)

    memes_dir = tmp_path / "memes"
    memes_dir.mkdir()
    (tmp_path / "categories.json").write_text("[]")

    def connect():
        conn = sqlite3.connect(tmp_path / "memes.db")
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.execute(
            "CREATE TABLE memes (id INTEGER PRIMARY KEY, filename TEXT, emotions TEXT, personas TEXT, description TEXT, send_mode TEXT)"
        )
        conn.executemany(
            "INSERT INTO memes VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "global.png", "开心", "*", "通用表情", "image"),
                (2, "alice.png", "开心,猫猫", "alice", "开心的猫猫", "sticker"),
                (3, "bob.png", "开心,猫猫", "bob", "其他人格", "sticker"),
                (4, "missing.png", "开心", "*", "已丢失的表情", "sticker"),
            ],
        )
    for filename in ("global.png", "alice.png", "bob.png"):
        PILImage.new("RGB", (8, 8), "red").save(memes_dir / filename)

    database = ModuleType(package + ".backend.db.database")
    database.get_db_conn = connect
    database.get_all_tag_embeddings = Mock(
        return_value={"开心": [1.0, 0.0], "猫猫": [0.0, 1.0]}
    )
    monkeypatch.setitem(sys.modules, database.__name__, database)

    def load(suffix, filename):
        name = package + suffix
        spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    load(".utils", "utils.py")
    helpers = load(".backend.core.helpers", "backend/core/helpers.py")
    mixin = load(".backend.core.config_mixin", "backend/core/config_mixin.py")
    load(".backend.core.emotion_handler", "backend/core/emotion_handler.py")
    tools = load(".backend.core.llm_tools", "backend/core/llm_tools.py")
    handlers = load(
        ".backend.handlers.event_handlers", "backend/handlers/event_handlers.py"
    )
    backend = sys.modules[package + ".backend"]
    backend.__dict__.update(
        CategoryManager=Mock(),
        CommandsHandler=object,
        EventHandlers=handlers.EventHandlers,
        MemeConfigMixin=mixin.MemeConfigMixin,
        send_meme=tools.send_meme,
        migrate_old_persona_tags_if_needed=helpers.migrate_old_persona_tags_if_needed,
        patch_onebot_serializer=Mock(),
        register_apis=Mock(),
        sync_tag_embeddings=AsyncMock(),
        sync_similarity_features=AsyncMock(),
    )
    main = load(".main", "main.py")
    context = SimpleNamespace(
        provider_manager=SimpleNamespace(
            personas=[
                {"id": "alice", "name": "Alice", "prompt": "  Original prompt.\n"}
            ],
            llm_tools=tool_manager,
        ),
        activate_llm_tool=Mock(),
        get_all_embedding_providers=Mock(return_value=[]),
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=None)
        ),
        persona_manager=SimpleNamespace(
            resolve_selected_persona=AsyncMock(return_value=("alice", None, None, None))
        ),
        get_config=Mock(return_value={}),
        get_all_stars=Mock(return_value=[]),
    )
    sender = main.MemeSender.__new__(main.MemeSender)
    sender.context = context
    sender.config = {"persona_settings": {"alice": {"meme_use_preference": "猫猫"}}}
    sender._last_mtime = (tmp_path / "categories.json").stat().st_mtime
    return SimpleNamespace(
        main=main, sender=sender, context=context, hooks=hooks, tool=tool
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["tag", "tool", "hybrid", True, False])
@pytest.mark.parametrize("giftia_mode", [False, True])
async def test_legacy_settings_leave_personas_untouched_and_enable_tool(
    meme_plugin, mode, giftia_mode
):
    context = meme_plugin.context
    original = context.provider_manager.personas[0]["prompt"]
    sender = meme_plugin.main.MemeSender(
        context,
        {
            "enable_llm_tool": mode,
            "meme_prompt": "Legacy instructions",
            "persona_blacklist": ["alice"],
            "enable_giftia_mode": giftia_mode,
            "emotion_llm_config": {"enable_emotion_llm": True},
            "persona_settings": {
                "alice": {"meme_preference": "cats", "meme_use_preference": "猫猫"}
            },
        },
    )
    await asyncio.sleep(0)
    await sender.reload_emotions()
    await asyncio.sleep(0)
    assert context.provider_manager.personas[0]["prompt"] == original
    context.activate_llm_tool.assert_called_once_with("send_meme")
    assert meme_plugin.tool.parameters["properties"]["image_url"]["description"] == (
        "Image hash." if giftia_mode else "要收录的图片 HTTP/HTTPS URL 或本地文件路径。"
    )
    names = {name for name, _ in meme_plugin.hooks}
    assert names.isdisjoint(
        {"on_llm_response", "on_decorating_result", "after_message_sent"}
    )
    assert ("event_message_type", "handle_direct_meme_trigger") not in meme_plugin.hooks
    assert ("llm_tool", "send_meme") in meme_plugin.hooks
    context.provider_manager.personas[0]["prompt"] = (
        "Updated while the plugin is running."
    )
    await sender.terminate()
    assert (
        context.provider_manager.personas[0]["prompt"]
        == "Updated while the plugin is running."
    )


@pytest.mark.asyncio
async def test_tool_search_selection_and_gif_send_are_session_scoped(meme_plugin):
    sender = meme_plugin.sender
    sender.config["interaction_config"] = {"convert_static_to_gif": True}
    event = SimpleNamespace(
        unified_msg_origin="test:group:one",
        send=AsyncMock(),
        get_platform_name=lambda: "test",
    )
    text = await sender.send_meme(event, query="开心")
    assert "开心的猫猫" in text
    assert "其他人格" not in text
    event.send.assert_not_awaited()

    other = SimpleNamespace(
        unified_msg_origin="test:group:two",
        send=AsyncMock(),
        get_platform_name=lambda: "test",
    )
    assert "请先传入" in await sender.send_meme(other, index=1)
    other.send.assert_not_awaited()

    async def inspect_send(chain):
        image = chain.chain[0]
        with PILImage.open(image.file) as converted:
            assert converted.format == "GIF"
        assert image.sub_type == 1
        assert image.meme_desc == "开心的猫猫"

    event.send.side_effect = inspect_send
    assert "成功发送" in await sender.send_meme(event, index=1)
    event.send.assert_awaited_once()
    assert not Path(event.send.call_args.args[0].chain[0].file).exists()
    assert "请先传入" in await sender.send_meme(event, index=1)


@pytest.mark.asyncio
async def test_giftia_candidates_and_components_preserve_persona_and_send_modes(
    meme_plugin,
):
    sender = meme_plugin.sender
    candidates = await sender.get_candidate_memes(
        persona_id="alice", query="开心", count=1
    )
    assert [m["id"] for m in candidates] == [2]
    assert candidates[0]["send_mode"] == "sticker"
    assert candidates[0]["score"] > 1000
    for query in ("", "no matching tags"):
        fallback = await sender.get_candidate_memes(
            persona_id="alice", query=query, count=10
        )
        assert {m["id"] for m in fallback} == {1, 2}
    assert await sender.get_candidate_memes(count=0) == []
    assert sender.get_meme_by_id("2")["personas"] == "alice"
    sticker = sender.build_meme_component("2")
    assert sticker.sub_type == 1
    assert sticker.meme_desc == "开心的猫猫"
    assert sender.build_meme_component(sender.get_meme_by_id(1)).sub_type == 0
    assert sender.build_meme_component(4) is None

    provider = SimpleNamespace(get_embedding=AsyncMock(return_value=[1.0, 0.0]))
    meme_plugin.context.get_all_embedding_providers.return_value = [provider]
    semantic = await sender.get_candidate_memes(
        persona_id="alice", query="高兴", count=2
    )
    assert [m["id"] for m in semantic] == [2, 1]
    provider.get_embedding.assert_awaited_once_with("高兴")


@pytest.mark.asyncio
async def test_legacy_tag_lookup_returns_persona_matches_without_sending(meme_plugin):
    sender = meme_plugin.sender
    sender.config["interaction_config"] = {
        "max_emotions_per_message": 0,
        "emotions_probability": 0,
    }
    meme_plugin.context.llm_generate = AsyncMock()
    event = SimpleNamespace(
        unified_msg_origin="test:group:one",
        send=AsyncMock(),
        get_platform_name=lambda: "test",
    )
    handler = importlib.import_module(
        f"{meme_plugin.main.__package__}.backend.core.emotion_handler"
    )
    original_prompt = meme_plugin.context.provider_manager.personas[0]["prompt"]

    candidates = await handler.get_direct_trigger_memes(sender, event, [" 开心 "])

    assert [m["id"] for m in candidates] == [2, 1]
    assert candidates[0]["filename"] == "alice.png"
    assert candidates[0]["send_mode"] == "sticker"
    assert meme_plugin.context.provider_manager.personas[0]["prompt"] == original_prompt
    event.send.assert_not_awaited()
    meme_plugin.context.llm_generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tags", [[], ["", "  "], ["no_matching_tag"]])
async def test_legacy_tag_lookup_returns_no_unrelated_fallback(meme_plugin, tags):
    handler = importlib.import_module(
        f"{meme_plugin.main.__package__}.backend.core.emotion_handler"
    )
    event = SimpleNamespace(
        unified_msg_origin="test:group:one", get_platform_name=lambda: "test"
    )

    assert await handler.get_direct_trigger_memes(meme_plugin.sender, event, tags) == []
