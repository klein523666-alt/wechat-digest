"""Utilities for extracting WeChat group names and messages."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

DECRYPTED_DB_DIR = Path(__file__).resolve().parent.parent / "decrypted_db"
WECHAT_MOCK_ENV = "WECHAT_DIGEST_MOCK"

TEXT_MSG_TYPE = 1
MSG_PLACEHOLDERS = {
    3: "[图片]",
    34: "[语音]",
    43: "[视频]",
    49: "[文件]",
}


def get_all_groups() -> list[str]:
    """Return all non-empty group chat names sorted by pinyin."""
    if _is_mock_mode():
        return ["产品讨论群", "投资交流群", "技术群"]

    try:
        _ensure_decrypted_db()
        groups: set[str] = set()
        for db_path in _iter_db_paths():
            try:
                with sqlite3.connect(db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT DISTINCT NickName
                        FROM Contact
                        WHERE UserName LIKE '%@chatroom'
                          AND NickName IS NOT NULL
                          AND TRIM(NickName) != ''
                        """
                    ).fetchall()
                groups.update((row[0] or "").strip() for row in rows if (row[0] or "").strip())
            except sqlite3.Error:
                continue

        return sorted(groups, key=_pinyin_sort_key)
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - exception normalization
        raise RuntimeError(f"读取群聊列表失败: {exc}") from exc


def get_messages(group_name: str, start: datetime, end: datetime) -> list[dict]:
    """Return normalized messages for a group in the given time range."""
    if _is_mock_mode():
        return _mock_messages(start, end)

    try:
        if not group_name or not group_name.strip():
            return []
        if end < start:
            return []

        _ensure_decrypted_db()
        chatroom_ids = _get_chatroom_ids_by_name(group_name.strip())
        if not chatroom_ids:
            return []

        messages: list[dict] = []
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())

        for db_path in _iter_db_paths():
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    messages.extend(_query_messages_from_connection(conn, chatroom_ids, start_ts, end_ts))
            except sqlite3.Error:
                continue

        messages.sort(key=lambda item: item["timestamp"])
        return messages
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - exception normalization
        raise RuntimeError(f"读取消息失败: {exc}") from exc


def _is_mock_mode() -> bool:
    return os.getenv(WECHAT_MOCK_ENV) == "1"


def _ensure_decrypted_db() -> None:
    if _has_decrypted_sqlite():
        return

    try:
        from pywxdump import batch_decrypt, read_info
    except Exception as exc:
        raise RuntimeError(f"无法导入 pywxdump: {exc}") from exc

    try:
        info = read_info()
    except Exception as exc:
        raise RuntimeError(f"读取微信信息失败: {exc}") from exc

    key = _extract_key(info)
    wx_path = _extract_wx_path(info)
    if not key:
        raise RuntimeError("请先登录PC端微信后重试")

    DECRYPTED_DB_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Different pywxdump versions expose different parameter names; try common patterns.
        try:
            batch_decrypt(wx_path=wx_path, key=key, out_path=str(DECRYPTED_DB_DIR))
        except TypeError:
            try:
                batch_decrypt(wx_path, key, str(DECRYPTED_DB_DIR))
            except TypeError:
                batch_decrypt(key=key, out_path=str(DECRYPTED_DB_DIR))
    except Exception as exc:
        raise RuntimeError(f"数据库解密失败: {exc}") from exc


def _extract_key(info: object) -> str:
    if isinstance(info, dict):
        return str(info.get("key") or "").strip()

    if isinstance(info, list):
        for item in info:
            if isinstance(item, dict):
                key = str(item.get("key") or "").strip()
                if key:
                    return key
    return ""


def _extract_wx_path(info: object) -> str | None:
    if isinstance(info, dict):
        return info.get("wx_path") or info.get("wx_dir")

    if isinstance(info, list):
        for item in info:
            if isinstance(item, dict):
                value = item.get("wx_path") or item.get("wx_dir")
                if value:
                    return value
    return None


def _has_decrypted_sqlite() -> bool:
    return DECRYPTED_DB_DIR.exists() and any(DECRYPTED_DB_DIR.rglob("*.db"))


def _iter_db_paths() -> Iterable[Path]:
    return sorted(DECRYPTED_DB_DIR.rglob("*.db"))


def _get_chatroom_ids_by_name(group_name: str) -> set[str]:
    result: set[str] = set()
    for db_path in _iter_db_paths():
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT UserName
                    FROM Contact
                    WHERE NickName = ? AND UserName LIKE '%@chatroom'
                    """,
                    (group_name,),
                ).fetchall()
            result.update((row[0] or "").strip() for row in rows if (row[0] or "").strip())
        except sqlite3.Error:
            continue
    return result


def _query_messages_from_connection(
    conn: sqlite3.Connection,
    chatroom_ids: set[str],
    start_ts: int,
    end_ts: int,
) -> list[dict]:
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(MSG)").fetchall()}
        if not columns:
            return []
    except sqlite3.Error:
        return []

    if not {"StrTalker", "Type", "CreateTime", "StrContent"}.issubset(columns):
        return []

    time_expr = "CreateTime / 1000" if _is_millisecond_timestamp(conn) else "CreateTime"
    placeholders = ",".join("?" for _ in chatroom_ids)
    sql = f"""
        SELECT StrTalker, Type, IsSender, CreateTime, StrContent
        FROM MSG
        WHERE StrTalker IN ({placeholders})
          AND {time_expr} >= ?
          AND {time_expr} <= ?
        ORDER BY CreateTime ASC
    """
    params: list = [*chatroom_ids, start_ts, end_ts]

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []

    records: list[dict] = []
    for row in rows:
        content = _normalize_content(row["Type"], row["StrContent"])
        sender = _extract_sender(int(row["IsSender"] or 0), str(row["StrContent"] or ""))
        records.append(
            {
                "sender": sender,
                "timestamp": _format_timestamp(int(row["CreateTime"] or 0)),
                "content": content,
            }
        )
    return records


def _is_millisecond_timestamp(conn: sqlite3.Connection) -> bool:
    try:
        value = conn.execute("SELECT MAX(CreateTime) FROM MSG").fetchone()[0]
    except sqlite3.Error:
        return False
    if value is None:
        return False
    return int(value) > 10_000_000_000


def _normalize_content(msg_type: int, raw_content: str) -> str:
    if msg_type == TEXT_MSG_TYPE:
        return _strip_group_prefix(raw_content)
    return MSG_PLACEHOLDERS.get(msg_type, "[文件]")


def _strip_group_prefix(content: str) -> str:
    if ":\n" in content:
        return content.split(":\n", 1)[1].strip()
    return content.strip()


def _extract_sender(is_sender: int, raw_content: str) -> str:
    if is_sender == 1:
        return "我"
    if ":\n" in raw_content:
        return raw_content.split(":\n", 1)[0].strip() or "未知"
    return "未知"


def _format_timestamp(raw_timestamp: int) -> str:
    if raw_timestamp > 10_000_000_000:
        raw_timestamp //= 1000
    return datetime.fromtimestamp(raw_timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _pinyin_sort_key(text: str) -> tuple:
    try:
        from pypinyin import Style, lazy_pinyin

        return tuple(lazy_pinyin(text, style=Style.NORMAL))
    except Exception:
        return (text,)


def _mock_messages(start: datetime, end: datetime) -> list[dict]:
    if end < start:
        return []

    scripted_messages = [
        ("王磊", "大家早上好，昨晚的新版本都体验了吗？"),
        ("李娜", "我测了下，登录页加载快了很多，赞！"),
        ("陈晨", "@王磊 你说的支付回调问题，今天要不要一起看？"),
        ("王磊", "可以，10点后我有空，先把复现步骤发群里。"),
        ("赵敏", "有人知道下午路演材料最后截止几点吗？"),
        ("周涛", "我问了运营，说是17:30之前上传。"),
        ("赵敏", "收到，谢谢～"),
        ("刘洋", "技术群那边在讨论接口超时，谁有日志截图？"),
        ("陈晨", "我这有，稍等我整理一下发你。"),
        ("王磊", "@刘洋 先看网关，昨天有一波流量峰值。"),
        ("李娜", "中午谁一起吃饭？我想去楼下新开的面馆。"),
        ("周涛", "+1，我12:10下楼。"),
        ("赵敏", "我也去，顺便聊下预算表。"),
        ("刘洋", "刚刚把日志传到共享盘了，路径在群公告。"),
        ("陈晨", "看到了，超时主要集中在14:05到14:20。"),
        ("王磊", "那我们先加熔断，再看是否要扩容。"),
        ("李娜", "今晚要不要发个简版周报给老板？"),
        ("周涛", "要的，我来起草第一版，大家补充。"),
        ("赵敏", "@周涛 记得把路演进展也写进去。"),
        ("王磊", "辛苦各位，今天目标：问题定位+方案确认。"),
    ]

    total = len(scripted_messages)
    interval = (end - start) / max(total - 1, 1)
    result: list[dict] = []
    for idx, (sender, content) in enumerate(scripted_messages):
        ts = start + interval * idx
        result.append(
            {
                "sender": sender,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "content": content,
            }
        )
    return result
