"""Unit and integration tests for crypto, persistence, helpers and handlers."""
from __future__ import annotations

import base64
import logging
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
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
from utils.log_utils import WebhookLogFilter
from utils.responses import ResponseKey, get_response

PASSWORD = "unit-test-master-password-123"


def _legacy_deterministic(value: str) -> str:
    """Reproduce the pre-fix deterministic format (password as salt/nonce)."""
    salt = PASSWORD.encode()[:32].ljust(32, b"0")
    nonce = PASSWORD.encode()[:12].ljust(12, b"0")
    key = _derive_key_cached(PASSWORD, salt)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, value.encode(), None)
    return base64.b64encode(salt + nonce + ciphertext).decode()


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


def test_nondeterministic_encryption_reuses_derived_key() -> None:
    """Every anonymous send used to pay a full PBKDF2 derivation (random salt)."""
    _derive_key_cached.cache_clear()
    enc = Encryptor(PASSWORD)
    enc.encrypt("first payload")
    enc.encrypt("second payload")
    info = _derive_key_cached.cache_info()
    assert info.misses == 1
    assert info.hits >= 1


def test_legacy_random_salt_ciphertext_still_decrypts() -> None:
    """Rows written before the cacheable salt must keep decrypting unchanged."""
    salt = os.urandom(32)
    nonce = os.urandom(12)
    key = _derive_key_cached(PASSWORD, salt)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, b"legacy value", None)
    blob = base64.b64encode(salt + nonce + ciphertext).decode()
    assert Encryptor(PASSWORD).decrypt(blob) == "legacy value"


def test_deterministic_ciphertext_does_not_leak_password() -> None:
    """The old salt/nonce were the password itself, stored in plain sight."""
    enc = Encryptor(PASSWORD)
    blob = base64.b64decode(enc.encrypt("secret value", deterministic=True))
    assert PASSWORD.encode() not in blob
    assert blob[:32] != PASSWORD.encode()[:32].ljust(32, b"0")
    assert blob[32:44] != PASSWORD.encode()[:12].ljust(12, b"0")


def test_legacy_deterministic_ciphertext_still_decrypts() -> None:
    assert Encryptor(PASSWORD).decrypt(_legacy_deterministic("legacy")) == "legacy"


def test_builder_disables_unused_job_queue() -> None:
    app = bot_creator._telegram_builder(
        "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"
    ).build()
    assert app._job_queue is None


def test_cold_modules_are_imported_lazily() -> None:
    import utils.secure_config as secure_config

    assert "InfisicalSDKClient" not in vars(secure_config)
    assert "GitHubChecker" not in vars(bot_creator)


def test_successful_webhook_access_logs_are_dropped() -> None:
    log_filter = WebhookLogFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1", "POST", "/webhook/123:abc", "1.1", 200),
        exc_info=None,
    )
    assert log_filter.filter(record) is False

    record.args = ("127.0.0.1", "POST", "/webhook/123:abc", "1.1", 403)
    assert log_filter.filter(record) is True


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


async def test_deterministic_migration_reencrypts_legacy_rows(tmp_path) -> None:
    enc = Encryptor(PASSWORD)
    db = DatabaseManager(str(tmp_path / "migration.db"))
    await db._init_task

    legacy_token = _legacy_deterministic("123:ABC")
    legacy_username = _legacy_deterministic("migrate_bot")
    legacy_admin = _legacy_deterministic("77")
    legacy_block_id = _legacy_deterministic("777")
    legacy_block_bu = _legacy_deterministic("migrate_bot")
    new_token = enc.encrypt("123:ABC", deterministic=True)
    new_block_id = enc.encrypt("777", deterministic=True)

    async with db._get_connection() as conn:
        await conn.execute(
            "DELETE FROM admins WHERE bot_token IN (?, ?)",
            (legacy_token, new_token),
        )
        await conn.execute(
            "DELETE FROM blocks WHERE blocked_user_id IN (?, ?)",
            (legacy_block_id, new_block_id),
        )
        await conn.execute(
            "INSERT INTO admins (bot_token, bot_username, admin_id)"
            " VALUES (?, ?, ?)",
            (legacy_token, legacy_username, legacy_admin),
        )
        await conn.execute(
            "INSERT INTO blocks (blocked_user_id, bot_username) VALUES (?, ?)",
            (legacy_block_id, legacy_block_bu),
        )
        await conn.commit()
        migrated = await db._migrate_deterministic_columns(conn)
        await conn.commit()
        assert migrated
        assert not await db._migrate_deterministic_columns(conn)
        await conn.commit()

    admin = AdminManager(db, enc)
    admin.db = db
    admin.encryptor = enc
    assert await admin.is_admin(77, "migrate_bot")
    assert await db.is_user_blocked(777, "migrate_bot")

    async with db._get_connection() as conn:
        async with conn.execute(
            "SELECT admin_id FROM admins WHERE bot_token = ?", (new_token,)
        ) as cursor:
            admin_row = await cursor.fetchone()
        async with conn.execute(
            "SELECT bot_username FROM blocks WHERE blocked_user_id = ?",
            (new_block_id,),
        ) as cursor:
            block_row = await cursor.fetchone()

    assert admin_row is not None
    assert enc.decrypt(admin_row[0]) == "77"
    assert block_row is not None
    assert enc.decrypt(block_row[0]) == "migrate_bot"
    assert PASSWORD.encode() not in base64.b64decode(new_token)

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


def test_callback_prefixes_are_unique() -> None:
    """The encrypted prefix is the DB primary key, so it must never repeat."""
    enc = Encryptor(PASSWORD)
    first = build_callback_payload(enc, "same payload", "r")
    second = build_callback_payload(enc, "same payload", "r")
    assert first.prefix != second.prefix
    assert first.callback_data != second.callback_data
    assert enc.decrypt(first.stored + first.suffix) == "same payload"
    assert enc.decrypt(second.stored + second.suffix) == "same payload"


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
