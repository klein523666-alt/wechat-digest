"""Generate daily summaries for group chat messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

SYSTEM_PROMPT = """
你是一个群聊日报助手，负责将微信群聊天记录整理成简洁的中文日报。
""".strip()

USER_PROMPT_TEMPLATE = """
以下是微信群「{group_name}」的聊天记录：

{messages_text}

请生成一份简洁日报，格式如下：
📌 核心话题（最多3条，每条不超过20字）
💡 重要信息（值得关注的决定、数据、链接，没有则省略）
❓ 待解决问题（没有则省略）

总字数控制在250字以内，直接输出日报内容，不加任何前缀。
""".strip()


def summarize(group_name: str, messages: list[dict], ai_config: dict) -> str:
    """Summarize messages with an AI model.

    Args:
        group_name: Group chat name.
        messages: Chat message items.
        ai_config: API configuration for anthropic or openai-compatible providers.

    Returns:
        Summary text, fallback raw text, or an error marker.
    """
    if not messages:
        return "（今日无消息）"

    messages_text = _build_messages_text(messages)
    if len(messages) < 5:
        return messages_text

    try:
        provider = (ai_config.get("provider") or "").strip()
        if provider == "anthropic":
            return _summarize_with_anthropic(group_name, messages_text, ai_config)
        if provider == "openai_compatible":
            return _summarize_with_openai_compatible(group_name, messages_text, ai_config)
        raise ValueError(f"不支持的 provider: {provider}")
    except Exception as exc:  # noqa: BLE001
        return f"（摘要生成失败：{exc}）"


def _build_messages_text(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        time_text = _extract_time_text(message)
        sender = _extract_sender(message)
        content = _extract_content(message)
        lines.append(f"[{time_text}] {sender}: {content}")
    return "\n".join(lines)


def _extract_time_text(message: dict[str, Any]) -> str:
    for key in ("time", "timestamp", "create_time", "datetime"):
        value = message.get(key)
        if value is None:
            continue
        if isinstance(value, datetime):
            return value.strftime("%H:%M")
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value).strftime("%H:%M")
        text = str(value).strip()
        parsed = _parse_time_string(text)
        if parsed:
            return parsed
        if len(text) >= 5:
            return text[-5:]
    return "--:--"


def _parse_time_string(text: str) -> str | None:
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ]
    for time_format in formats:
        try:
            return datetime.strptime(text, time_format).strftime("%H:%M")
        except ValueError:
            continue
    return None


def _extract_sender(message: dict[str, Any]) -> str:
    for key in ("sender", "sender_name", "nickname", "name", "from"):
        value = message.get(key)
        if value:
            return str(value)
    return "未知发送人"


def _extract_content(message: dict[str, Any]) -> str:
    for key in ("content", "text", "message", "msg"):
        value = message.get(key)
        if value is not None:
            text = str(value).strip()
            return text or "（空消息）"
    return "（空消息）"


def _build_user_prompt(group_name: str, messages_text: str) -> str:
    return USER_PROMPT_TEMPLATE.format(group_name=group_name, messages_text=messages_text)


def _summarize_with_anthropic(group_name: str, messages_text: str, ai_config: dict[str, Any]) -> str:
    client = Anthropic(api_key=ai_config.get("api_key"), base_url=ai_config.get("base_url"))
    response = client.messages.create(
        model=ai_config.get("model"),
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(group_name, messages_text),
            }
        ],
    )
    text_blocks = [
        block.text.strip()
        for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    result = "\n".join(text_blocks).strip()
    if not result:
        raise RuntimeError("Anthropic 返回空内容")
    return result


def _summarize_with_openai_compatible(
    group_name: str,
    messages_text: str,
    ai_config: dict[str, Any],
) -> str:
    client = OpenAI(
        base_url=ai_config.get("base_url"),
        api_key=ai_config.get("api_key"),
    )
    response = client.chat.completions.create(
        model=ai_config.get("model"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(group_name, messages_text),
            },
        ],
        temperature=0.2,
    )
    result = (response.choices[0].message.content or "").strip()
    if not result:
        raise RuntimeError("OpenAI 兼容接口返回空内容")
    return result
