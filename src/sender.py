"""Telegram message sending utilities for wechat-digest."""

from __future__ import annotations

import os

import requests

WECHAT_MOCK_ENV = "WECHAT_DIGEST_MOCK"


def _escape_html(text: str) -> str:
    """Escape HTML-sensitive characters for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_report(report_text: str, bot_token: str, chat_id: str) -> bool:
    """Send a report to Telegram in HTML mode.

    Args:
        report_text: Report content before escaping.
        bot_token: Telegram bot token.
        chat_id: Target chat id.

    Returns:
        True if sent successfully, otherwise False.
    """
    if _is_mock_mode():
        return True

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": _escape_html(report_text),
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
    except requests.RequestException as exc:
        print(f"发送 Telegram 消息失败：{exc}")
        return False

    if response.ok:
        return True

    print(
        "发送 Telegram 消息失败："
        f"HTTP {response.status_code} - {response.text}"
    )
    return False


def build_report(date_label: str, group_summaries: list[tuple[str, str]]) -> str:
    """Build the digest message with a fixed display template."""
    lines = [
        f"📊 微信群日报 · {date_label}",
        "━━━━━━━━━━━━━━",
    ]

    for group_name, summary in group_summaries:
        lines.append(f"💬 {group_name}")
        lines.append("")
        lines.append(summary)
        lines.append("")

    lines.extend(
        [
            "━━━━━━━━━━━━━━",
            "🤖 AI 自动生成 · wechat-digest",
        ]
    )

    return "\n".join(lines)


def test_connection(bot_token: str, chat_id: str) -> tuple[bool, str]:
    """Send a test message to verify Telegram connection settings."""
    if _is_mock_mode():
        return True, ""

    test_message = "✅ wechat-digest 连接测试成功"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": _escape_html(test_message),
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
    except requests.RequestException as exc:
        return False, str(exc)

    if response.ok:
        return True, ""

    return False, f"HTTP {response.status_code} - {response.text}"


def _is_mock_mode() -> bool:
    value = (os.getenv(WECHAT_MOCK_ENV) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}
