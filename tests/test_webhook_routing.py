"""Regression tests for main-bot vs child-bot webhook routing."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.exceptions import HTTPException
from telegram import Bot

import bot_creator

MAIN_TOKEN = "123456:AAHmain-token"
CHILD_TOKEN = "654321:AAHchild-token"
SECRET = "test-secret"


class FakeApp:
    def __init__(self) -> None:
        self.bot = Bot("123456:AAHfake")
        self.running = True
        self.update_queue: asyncio.Queue = asyncio.Queue()


class FakeRequest:
    def __init__(
        self,
        data: dict,
        secret: str = SECRET,
        path_token: str = MAIN_TOKEN,
    ) -> None:
        self.headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.path_params = {"bot_token": path_token}
        self._data = data

    async def json(self) -> dict:
        return self._data


def update_payload(update_id: int = 1, chat_type: str = "private") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": 1, "type": chat_type},
            "from": {"id": 1, "is_bot": False, "first_name": "Test"},
            "text": "hello",
        },
    }


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_creator, "MAIN_BOT_TOKEN", MAIN_TOKEN)
    monkeypatch.setattr(bot_creator, "TG_SECRET_TOKEN", SECRET)
    bot_creator.PROCESSED_UPDATES.clear()


async def test_main_bot_updates_use_main_application(monkeypatch: pytest.MonkeyPatch) -> None:
    main_app = FakeApp()
    get_application = AsyncMock()
    monkeypatch.setattr(bot_creator, "main_bot_application", main_app)
    monkeypatch.setattr(bot_creator, "get_application", get_application)

    response = await bot_creator.webhook_handler(
        FakeRequest(update_payload(1)),
    )

    assert json.loads(response.body)["status"] == "ok"
    assert main_app.update_queue.qsize() == 1
    get_application.assert_not_awaited()


async def test_child_bot_updates_use_child_application(monkeypatch: pytest.MonkeyPatch) -> None:
    child_app = FakeApp()
    get_application = AsyncMock(return_value=child_app)
    monkeypatch.setattr(bot_creator, "main_bot_application", FakeApp())
    monkeypatch.setattr(bot_creator, "get_application", get_application)

    response = await bot_creator.webhook_handler(
        FakeRequest(update_payload(2), path_token=CHILD_TOKEN),
    )

    assert json.loads(response.body)["status"] == "ok"
    assert child_app.update_queue.qsize() == 1
    get_application.assert_awaited_once_with(CHILD_TOKEN)


async def test_duplicate_update_is_not_queued_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    main_app = FakeApp()
    monkeypatch.setattr(bot_creator, "main_bot_application", main_app)
    monkeypatch.setattr(bot_creator, "get_application", AsyncMock())

    first = await bot_creator.webhook_handler(FakeRequest(update_payload(3)))
    second = await bot_creator.webhook_handler(FakeRequest(update_payload(3)))

    assert json.loads(first.body)["status"] == "ok"
    assert json.loads(second.body)["message"] == "duplicate"
    assert main_app.update_queue.qsize() == 1


async def test_invalid_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_creator, "main_bot_application", FakeApp())
    with pytest.raises(HTTPException) as exc:
        await bot_creator.webhook_handler(
            FakeRequest(update_payload(4), secret="wrong"),
        )
    assert exc.value.status_code == 403


async def test_non_private_update_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    main_app = FakeApp()
    monkeypatch.setattr(bot_creator, "main_bot_application", main_app)
    response = await bot_creator.webhook_handler(
        FakeRequest(update_payload(5, chat_type="group")),
    )
    assert json.loads(response.body)["message"] == "ignored non-private update"
    assert main_app.update_queue.qsize() == 0


async def test_asgi_webhook_route_and_json_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real Starlette route, not just the handler function."""
    main_app = FakeApp()
    monkeypatch.setattr(bot_creator, "MAIN_BOT_TOKEN", MAIN_TOKEN)
    monkeypatch.setattr(bot_creator, "TG_SECRET_TOKEN", SECRET)
    monkeypatch.setattr(bot_creator, "main_bot_application", main_app)
    bot_creator.PROCESSED_UPDATES.clear()

    transport = httpx.ASGITransport(app=bot_creator.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.post(
            f"/webhook/{MAIN_TOKEN}",
            json=update_payload(20),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "ok"
        assert main_app.update_queue.qsize() == 1

        denied = await client.post(
            f"/webhook/{MAIN_TOKEN}",
            json=update_payload(21),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert denied.status_code == 403
        assert denied.json() == {"detail": "Invalid secret token"}


async def test_asgi_health_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_creator, "_main_bot_is_running", lambda: True)
    bot_creator.app.state.main_bot_ready = True
    transport = httpx.ASGITransport(app=bot_creator.app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            ok = await client.get("/health")
            assert ok.status_code == 200
            assert ok.json()["status"] == "healthy"

            head = await client.head("/health")
            assert head.status_code == 200

            monkeypatch.setattr(bot_creator, "_main_bot_is_running", lambda: False)
            bot_creator.app.state.main_bot_ready = False
            unhealthy = await client.get("/health")
            assert unhealthy.status_code == 503
            assert unhealthy.json() == {"detail": "main bot is not running"}
    finally:
        bot_creator.app.state.main_bot_ready = False


def test_webhook_matches_url_and_update_types() -> None:
    desired = ["message", "callback_query"]
    info = SimpleNamespace(
        url="https://example.test/webhook/main",
        allowed_updates=("message", "callback_query"),
    )
    assert bot_creator._webhook_matches(info, info.url, desired)

    assert not bot_creator._webhook_matches(
        SimpleNamespace(url=info.url, allowed_updates=("message",)),
        info.url,
        desired,
    )
    assert not bot_creator._webhook_matches(
        SimpleNamespace(url=info.url, allowed_updates=None),
        info.url,
        desired,
    )
    assert not bot_creator._webhook_matches(
        SimpleNamespace(url="https://other.test", allowed_updates=tuple(desired)),
        info.url,
        desired,
    )
