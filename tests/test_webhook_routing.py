"""Regression tests for main-bot vs child-bot webhook routing."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
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
    def __init__(self, data: dict, secret: str = SECRET) -> None:
        self.headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
        self.client = SimpleNamespace(host="127.0.0.1")
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
        MAIN_TOKEN,
        FakeRequest(update_payload(1)),
    )

    assert response["status"] == "ok"
    assert main_app.update_queue.qsize() == 1
    get_application.assert_not_awaited()


async def test_child_bot_updates_use_child_application(monkeypatch: pytest.MonkeyPatch) -> None:
    child_app = FakeApp()
    get_application = AsyncMock(return_value=child_app)
    monkeypatch.setattr(bot_creator, "main_bot_application", FakeApp())
    monkeypatch.setattr(bot_creator, "get_application", get_application)

    response = await bot_creator.webhook_handler(
        CHILD_TOKEN,
        FakeRequest(update_payload(2)),
    )

    assert response["status"] == "ok"
    assert child_app.update_queue.qsize() == 1
    get_application.assert_awaited_once_with(CHILD_TOKEN)


async def test_duplicate_update_is_not_queued_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    main_app = FakeApp()
    monkeypatch.setattr(bot_creator, "main_bot_application", main_app)
    monkeypatch.setattr(bot_creator, "get_application", AsyncMock())

    first = await bot_creator.webhook_handler(MAIN_TOKEN, FakeRequest(update_payload(3)))
    second = await bot_creator.webhook_handler(MAIN_TOKEN, FakeRequest(update_payload(3)))

    assert first["status"] == "ok"
    assert second["message"] == "duplicate"
    assert main_app.update_queue.qsize() == 1


async def test_invalid_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_creator, "main_bot_application", FakeApp())
    with pytest.raises(HTTPException) as exc:
        await bot_creator.webhook_handler(
            MAIN_TOKEN,
            FakeRequest(update_payload(4), secret="wrong"),
        )
    assert exc.value.status_code == 403


async def test_non_private_update_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    main_app = FakeApp()
    monkeypatch.setattr(bot_creator, "main_bot_application", main_app)
    response = await bot_creator.webhook_handler(
        MAIN_TOKEN,
        FakeRequest(update_payload(5, chat_type="group")),
    )
    assert response["message"] == "ignored non-private update"
    assert main_app.update_queue.qsize() == 0


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
