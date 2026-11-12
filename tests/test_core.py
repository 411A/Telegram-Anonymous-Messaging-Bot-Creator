"""Unit and integration tests for crypto, persistence, helpers and handlers."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.constants import ParseMode

import bot_creator
from handlers.anonymous_handler import (
    build_callback_payload,
    calculate_message_delay,
    format_delay,
)
from utils.db_utils import (
    AdminManager,
    DatabaseManager,
    Encryptor,
    _derive_key_cached,
)
from utils.github_checker import GitHubChecker
from utils.helpers import (
    check_language_availability,
    extract_bot_token,
    generate_anonymous_id,
)
from utils.responses import ResponseKey, get_response

PASSWORD = "unit-test-master-password-123"


def test_encryptor_roundtrip_and_determinism() -> None:
    enc = Encryptor(PASSWORD)
    deterministic_a = enc.encrypt("same value", deterministic=True)
    deterministic_b = enc.encrypt("same value", deterministic=True)
    assert deterministic_a == deterministic_b
    assert enc.decrypt(deterministic_a) == "same value"

    random_a = enc.encrypt("same value")
    random_b = enc.encrypt("same value")
    assert random_a != random_b
    assert enc.decrypt(random_a) == "same value"
    assert enc.decrypt(random_b) == "same value"


def test_derived_key_cache_reuses_key() -> None:
    _derive_key_cached.cache_clear()
    salt = b"s" * 32
    first = _derive_key_cached(PASSWORD, salt)
    second = _derive_key_cached(PASSWORD, salt)
    assert first == second
    assert _derive_key_cached.cache_info().hits >= 1


async def test_database_crud_and_admin_flows(tmp_path) -> None:
    enc = Encryptor(PASSWORD)
    db = DatabaseManager(str(tmp_path / "test.db"))
    await db._init_task

    assert await db.store_partial_hash("prefix1", "stored1", "messages", "2026-11")
    assert await db.get_full_hash_by_prefix("prefix1", "suffix1", "messages") == "stored1suffix1"
    assert await db.remove_partial_hash("prefix1", "messages")

    assert await db.store_partial_hash("prefix2", "stored2", "reads")
    assert await db.get_full_hash_by_prefix("prefix2", "suffix2", "reads") == "stored2suffix2"
    assert await db.remove_partial_hash("prefix2", "reads")

    assert await db.block_user(777, "unit_test_bot")
    assert await db.is_user_blocked(777, "unit_test_bot")
    assert await db.unblock_user(777, "unit_test_bot")
    assert not await db.is_user_blocked(777, "unit_test_bot")

    admin = AdminManager(db, enc)
    admin.db = db
    admin.encryptor = enc
    assert await admin.add_admin("123:ABC", "unit_test_bot", 77)
    assert await admin.is_admin(77, "unit_test_bot")
    assert await admin.get_admin_id_from_bot("unit_test_bot") == 77

    encrypted_token = enc.encrypt("123:ABC", deterministic=True)
    assert await db.remove_bot_entry(encrypted_token)

    await db.close_all()


def test_helper_functions() -> None:
    assert extract_bot_token("prefix 12345:ABC_def-1 suffix") == "12345:ABC_def-1"
    assert extract_bot_token("no token here") == ""
    assert check_language_availability("fa") == "fa"
    assert check_language_availability("en-US") == "en"
    assert check_language_availability(None) == "en"

    anon_a = generate_anonymous_id(1, "Ali", with_history=True)
    anon_b = generate_anonymous_id(1, "Ali", with_history=True)
    assert anon_a == anon_b
    assert anon_a.startswith("#")
    assert len(anon_a) == 11

    anon_random = generate_anonymous_id(1, "Ali", with_history=False)
    assert anon_random and not anon_random.startswith("#")


def test_delay_calculation_and_formatting() -> None:
    timestamp_ns = time.time_ns() - 61 * 1_000_000_000
    delay = calculate_message_delay(timestamp_ns)
    assert delay is not None and delay >= 60
    assert "minute" in format_delay(delay, "en")
    assert "دقیقه" in format_delay(delay, "fa")
    assert calculate_message_delay(time.time_ns()) is None


def test_callback_payload_reconstruction() -> None:
    enc = Encryptor(PASSWORD)
    payload = build_callback_payload(enc, "1|2|3", "r")
    assert payload.callback_data == f"r|{payload.prefix}|{payload.suffix}"
    assert enc.decrypt(payload.stored + payload.suffix) == "1|2|3"


def test_localized_responses() -> None:
    english = get_response(ResponseKey.PROVIDE_TOKEN, "en")
    persian = get_response(ResponseKey.PROVIDE_TOKEN, "fa")
    assert "/register BOT_TOKEN" in english
    assert "/register BOT_TOKEN" in persian


async def test_main_about_builds_ton_button() -> None:
    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply)
    user = SimpleNamespace(id=1, language_code="en")
    update = SimpleNamespace(effective_message=message, effective_user=user)

    await bot_creator.main_about(update, None)

    reply.assert_awaited_once()
    kwargs = reply.await_args.kwargs
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert kwargs["do_quote"] is True
    assert kwargs["reply_markup"].inline_keyboard[0][0].url == (
        "ton://transfer/TechKraken.ton"
    )


async def test_main_start_uses_registration_welcome(monkeypatch) -> None:
    monkeypatch.setattr(bot_creator, "MAIN_BOT_USERNAME", "HidEgoBot")
    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply)
    user = SimpleNamespace(id=1, language_code="en")
    update = SimpleNamespace(effective_message=message, effective_user=user)

    await bot_creator.main_start(update, None)

    reply.assert_awaited_once()
    text = reply.await_args.args[0]
    assert "/register BOT_TOKEN" in text
    assert "Bot Creation Guide Video" in text


def test_docker_safetycheck_ignores_repo_only_files(monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_ENV", "1")
    checker = GitHubChecker(
        repo_owner="411A",
        repo_name="Telegram-Anonymous-Messaging-Bot-Creator",
    )
    assert checker._is_ignored("requirements-dev.txt")
    assert checker._is_ignored("src/assets/Guide-Telegram-Bot-HidEgoBot.mp4")
    assert checker._is_ignored(".github/workflows/docker-publish.yml")
    assert checker._is_ignored("tests/test_core.py")
    assert not checker._is_ignored("src/bot_creator.py")
