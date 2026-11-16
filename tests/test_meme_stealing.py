import base64
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from PIL import Image
from quart import Quart

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def stealing(tmp_path, monkeypatch):
    """Load collection code with real AstrBot decision types and isolated services.

    Args:
        tmp_path: Temporary working directory for AstrBot import side effects.
        monkeypatch: Fixture restoring imported modules after each test.

    Returns:
        Collection modules, a configured sender, and a small PNG image.
    """
    monkeypatch.chdir(tmp_path)
    from astrbot.api.provider import DecisionBooleanAnswer, DecisionBooleanQuestion
    from astrbot.core.provider.decision import DecisionService
    from astrbot.core.provider.sources.gemini_decision_source import (
        GeminiDecisionProvider,
    )
    from astrbot.core.provider.sources.openai_decision_source import (
        OpenAIDecisionProvider,
    )

    package = "meme_stealing_test"
    for suffix in (
        "",
        ".backend",
        ".backend.core",
        ".backend.db",
        ".backend.handlers",
        ".backend.web",
        ".backend.web.api",
    ):
        module = ModuleType(package + suffix)
        module.__path__ = [str(PLUGIN_ROOT / suffix.lstrip(".").replace(".", "/"))]
        monkeypatch.setitem(sys.modules, module.__name__, module)

    database = ModuleType(package + ".backend.db.database")
    database.get_db_conn = Mock()
    database.get_steal_attempt = Mock(return_value=None)
    database.save_steal_attempt = Mock()
    database.increment_image_seen_count = Mock(return_value=2)
    monkeypatch.setitem(sys.modules, database.__name__, database)
    models = ModuleType(package + ".backend.db.models")
    for name in (
        "save_and_register_meme",
        "batch_convert_to_gif",
        "batch_copy_emojis",
        "batch_delete_emojis",
        "batch_move_emojis",
        "move_emoji_to_category",
    ):
        setattr(models, name, Mock())
    monkeypatch.setitem(sys.modules, models.__name__, models)

    def load(suffix, filename):
        name = package + suffix
        spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    load(".utils", "utils.py")
    load(".backend.core.helpers", "backend/core/helpers.py")
    mixin = load(".backend.core.config_mixin", "backend/core/config_mixin.py")
    collector = load(
        ".backend.handlers.meme_stealer", "backend/handlers/meme_stealer.py"
    )
    tools = load(".backend.core.llm_tools", "backend/core/llm_tools.py")
    batch = load(".backend.web.api.batch", "backend/web/api/batch.py")

    sender = mixin.MemeConfigMixin()
    sender.config = {
        "multimodal_config": {"meme_decision_provider_id": "decision-test"},
        "similarity_dedup_config": {"enable_similarity_dedup": False},
    }
    sender.context = SimpleNamespace(
        decision=SimpleNamespace(
            ask=AsyncMock(
                return_value={
                    "is_meme": DecisionBooleanAnswer(0.9),
                    "matches_preference": DecisionBooleanAnswer(0.8),
                }
            )
        ),
        llm_generate=AsyncMock(
            return_value=SimpleNamespace(
                completion_text='{"match": true, "reason": "符合偏好"}'
            )
        ),
        get_current_chat_provider_id=AsyncMock(return_value="current-chat"),
    )
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(stream, format="PNG")
    return SimpleNamespace(
        collector=collector,
        tools=tools,
        batch=batch,
        database=database,
        sender=sender,
        event=SimpleNamespace(unified_msg_origin="test:group:1"),
        content=stream.getvalue(),
        answer=DecisionBooleanAnswer,
        question_type=DecisionBooleanQuestion,
        decision_service=DecisionService,
        adapters={"gemini": GeminiDecisionProvider, "openai": OpenAIDecisionProvider},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("meme_probability", "preference_probability", "accepted", "reason"),
    [
        (0.9, 0.8, True, "符合"),
        (0.5, 0.5, True, "符合"),
        (0.49, 0.9, False, "不属于表情包"),
        (0.9, 0.49, False, "不符合当前人格"),
    ],
)
async def test_decision_requires_both_checks(
    stealing, meme_probability, preference_probability, accepted, reason
):
    sender = stealing.sender
    sender.context.decision.ask.return_value = {
        "is_meme": stealing.answer(meme_probability),
        "matches_preference": stealing.answer(preference_probability),
    }

    result, message = await stealing.collector._check_meme_preference_match(
        sender, stealing.event, stealing.content, "png", "喜欢猫猫"
    )

    assert result is accepted
    assert reason in message
    call = sender.context.decision.ask.call_args
    assert call.kwargs["provider_id"] == "decision-test"
    questions = call.args[0]
    assert set(questions) == {"is_meme", "matches_preference"}
    assert all(isinstance(q, stealing.question_type) for q in questions.values())
    text, media = call.kwargs["state"].content
    assert "喜欢猫猫" in text
    assert media.type == "image"
    assert media.mime_type == "image/png"
    assert base64.b64decode(media.data) == stealing.content
    sender.context.decision.ask.assert_awaited_once()
    sender.context.llm_generate.assert_not_awaited()
    sender.context.get_current_chat_provider_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_animated_decision_receives_ordered_frames(stealing):
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    stream = io.BytesIO()
    frames[0].save(stream, format="GIF", save_all=True, append_images=frames[1:])

    result, _ = await stealing.collector._check_meme_preference_match(
        stealing.sender, stealing.event, stream.getvalue(), "gif", "喜欢猫猫"
    )

    assert result is True
    text, *media = stealing.sender.context.decision.ask.call_args.kwargs[
        "state"
    ].content
    assert "2 张关键帧" in text
    assert len(media) == 2
    for part, expected_channel in zip(media, (0, 2)):
        assert part.mime_type == "image/jpeg"
        with Image.open(io.BytesIO(base64.b64decode(part.data))) as frame:
            pixel = frame.getpixel((0, 0))
            assert pixel[expected_channel] > 200


@pytest.mark.asyncio
@pytest.mark.parametrize("decision_id", [None, "", "   "])
@pytest.mark.parametrize("chat_id", ["", "configured-chat"])
async def test_unconfigured_decision_preserves_original_chat_flow(
    stealing, monkeypatch, decision_id, chat_id
):
    settings = stealing.sender.config["multimodal_config"]
    settings.clear()
    if decision_id is not None:
        settings["meme_decision_provider_id"] = decision_id
    settings["multimodal_llm_provider_id"] = chat_id
    monkeypatch.setitem(sys.modules, "astrbot.api.provider", ModuleType("legacy_api"))

    result, reason = await stealing.collector._check_meme_preference_match(
        stealing.sender, stealing.event, stealing.content, "png", "喜欢猫猫"
    )

    assert result is True
    assert reason == "符合偏好"
    call = stealing.sender.context.llm_generate.call_args
    assert call.kwargs["chat_provider_id"] == (chat_id or "current-chat")
    assert "不属于的直接判false" in call.kwargs["prompt"]
    assert "喜欢猫猫" in call.kwargs["prompt"]
    assert call.kwargs["image_urls"][0].startswith("data:image/png;base64,")
    stealing.sender.context.decision.ask.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["request", "missing", "invalid", "legacy_api"])
async def test_decision_failure_is_retryable_and_does_not_fall_back(
    stealing, monkeypatch, failure
):
    ask = stealing.sender.context.decision.ask
    if failure == "request":
        ask.side_effect = RuntimeError("request failed")
    elif failure == "missing":
        ask.return_value = {}
    elif failure == "invalid":
        ask.return_value["is_meme"] = stealing.answer(float("nan"))
    else:
        monkeypatch.setitem(
            sys.modules, "astrbot.api.provider", ModuleType("legacy_api")
        )

    message = await stealing.collector._check_preference(
        stealing.sender,
        stealing.event,
        "alice",
        "image-hash",
        stealing.content,
        "png",
        "喜欢猫猫",
    )

    assert "收录判定失败" in message
    assert "Gemini" in message
    stealing.database.save_steal_attempt.assert_not_called()
    stealing.sender.context.llm_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_decision_rejection_is_cached_with_reason(stealing):
    stealing.sender.context.decision.ask.return_value["is_meme"] = stealing.answer(0.1)
    message = await stealing.collector._check_preference(
        stealing.sender,
        stealing.event,
        "alice",
        "image-hash",
        stealing.content,
        "png",
        "喜欢猫猫",
    )

    assert "不属于表情包" in message
    stealing.database.save_steal_attempt.assert_called_once_with(
        "image-hash", "alice", False, "图片不属于表情包范畴。"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["manual", "auto"])
@pytest.mark.parametrize("accepted", [True, False])
async def test_collection_entrypoints_share_the_decision_gate(
    stealing, monkeypatch, entrypoint, accepted
):
    collector = stealing.collector
    sender = stealing.sender
    sender.context.decision.ask.return_value["is_meme"] = stealing.answer(
        0.9 if accepted else 0.1
    )
    classify = AsyncMock(return_value=(["猫猫"], [], "一只猫", None))
    persist = AsyncMock(return_value="saved")
    monkeypatch.setattr(collector, "_resolve_categories", classify)
    monkeypatch.setattr(collector, "_persist_stolen_meme", persist)
    monkeypatch.setattr(
        collector,
        "resolve_persona_preference",
        AsyncMock(return_value=("alice", "喜欢猫猫", None)),
    )
    if entrypoint == "manual":
        await stealing.tools.steal_meme(
            sender,
            stealing.event,
            categories=["猫猫"],
            image_content=stealing.content,
            image_hash="image-hash",
            image_type="png",
        )
    else:
        stealing.database.get_db_conn.return_value.cursor.return_value.fetchone.return_value = None
        monkeypatch.setattr(
            collector,
            "extract_event_image_url",
            Mock(return_value="https://test/a.png"),
        )
        monkeypatch.setattr(
            collector,
            "download_image",
            AsyncMock(return_value=(stealing.content, "png", "image-hash", None)),
        )
        await collector.auto_steal_meme(sender, stealing.event)

    sender.context.decision.ask.assert_awaited_once()
    assert classify.await_count == int(accepted)
    assert persist.await_count == int(accepted)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["gemini", "openai"])
async def test_real_decision_adapters_receive_explicit_images(stealing, adapter):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["input"][1] == {
            "type": "image",
            "mime_type": "image/png",
            "data": base64.b64encode(stealing.content).decode(),
        }
        assert set(payload["questions"]) == {"q0", "q1"}
        return httpx.Response(
            200,
            json={
                "answers": {
                    key: {"type": "noul", "noul": 0.9, "confidence": 0.9}
                    for key in ("q0", "q1")
                }
            },
        )

    provider = stealing.adapters[adapter](
        {"id": "decision-test", "model": "test", "api_base": "https://test/v1"},
        {},
        transport=httpx.MockTransport(handler),
    )
    manager = SimpleNamespace(get_provider_by_id=AsyncMock(return_value=provider))
    stealing.sender.context.decision = stealing.decision_service(manager)
    try:
        result, reason = await stealing.collector._check_meme_preference_match(
            stealing.sender, stealing.event, stealing.content, "png", "喜欢猫猫"
        )
    finally:
        await provider.terminate()

    if adapter == "gemini":
        assert result is True
        assert len(requests) == 1
    else:
        assert result is None
        assert "Gemini" in reason
        assert requests == []


@pytest.mark.asyncio
async def test_provider_dropdown_lists_decisions_separately(stealing):
    chat = SimpleNamespace(meta=lambda: SimpleNamespace(id="chat"), name="Chat")
    decision = SimpleNamespace(
        meta=lambda: SimpleNamespace(id="decision"), name="Decision"
    )
    context = SimpleNamespace(
        get_all_providers=Mock(return_value=[chat]),
        provider_manager=SimpleNamespace(decision_provider_insts=[decision]),
    )
    app = Quart(__name__)
    app.config["PLUGIN_CONFIG"] = {"context": context}
    app.add_url_rule("/providers", view_func=stealing.batch.get_providers)
    client = app.test_client()

    response = await client.get("/providers")
    assert response.status_code == 200
    assert await response.get_json() == [{"id": "chat", "name": "Chat"}]
    response = await client.get("/providers?provider_type=decision")
    assert response.status_code == 200
    assert await response.get_json() == [{"id": "decision", "name": "Decision"}]
    del context.provider_manager.decision_provider_insts
    response = await client.get("/providers?provider_type=decision")
    assert await response.get_json() == []


@pytest.mark.parametrize("nested", [True, False])
def test_decision_provider_config_supports_both_formats(stealing, nested):
    stealing.sender.config = {"meme_decision_provider_id": "selected"}
    if nested:
        stealing.sender.config = {"multimodal_config": stealing.sender.config}
    assert stealing.sender.meme_decision_provider_id == "selected"
