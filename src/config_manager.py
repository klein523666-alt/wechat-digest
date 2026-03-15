"""Configuration manager utilities."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
CONFIG_EXAMPLE_PATH = PROJECT_ROOT / "config.example.json"


def load_config() -> dict:
    """Load config.json from project root.

    If config.json does not exist, initialize it by copying config.example.json.
    """
    if not CONFIG_PATH.exists():
        shutil.copyfile(CONFIG_EXAMPLE_PATH, CONFIG_PATH)

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_config(data: dict) -> None:
    """Save configuration data to config.json with UTF-8 encoding."""
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_selected_groups() -> list[str]:
    """Return selected group names from config."""
    config = load_config()
    groups = config.get("selected_groups", [])
    return groups if isinstance(groups, list) else []


def save_selected_groups(groups: list[str]) -> None:
    """Save selected group names to config."""
    config = load_config()
    config["selected_groups"] = groups
    save_config(config)


def get_ai_config() -> dict:
    """Return AI configuration from config."""
    config = load_config()
    ai_config = config.get("ai", {})
    if not isinstance(ai_config, dict):
        ai_config = {}

    return {
        "api_key": ai_config.get("api_key", ""),
        "base_url": ai_config.get("base_url", ""),
        "model": ai_config.get("model", ""),
        "provider": ai_config.get("provider", ""),
    }


def save_ai_config(ai_config: dict) -> None:
    """Save AI configuration into config['ai']."""
    config = load_config()
    config["ai"] = {
        "api_key": ai_config.get("api_key", ""),
        "base_url": ai_config.get("base_url", ""),
        "model": ai_config.get("model", ""),
        "provider": ai_config.get("provider", ""),
    }
    save_config(config)


def get_report_range(report_days: int) -> tuple[datetime, datetime]:
    """Return report time range in local timezone based on report_days."""
    now = datetime.now().astimezone()
    day_offset_mapping = {1: 0, 2: 1, 3: 2, 7: 7}
    day_offset = day_offset_mapping.get(report_days, max(report_days - 1, 0))

    start_date = (now - timedelta(days=day_offset)).date()
    start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=now.tzinfo)
    return start_datetime, now
