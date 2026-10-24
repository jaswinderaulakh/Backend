"""Loads the files in config/ (thresholds, rules, CPWD rates). Read-only."""
import json
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.settings import PROJECT_ROOT

CONFIG_DIR: Path = PROJECT_ROOT / "config"


@lru_cache
def load_thresholds() -> dict:
    return yaml.safe_load((CONFIG_DIR / "thresholds.yaml").read_text(encoding="utf-8"))


@lru_cache
def load_campus_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "campus.yaml").read_text(encoding="utf-8"))


@lru_cache
def load_security_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "security.yaml").read_text(encoding="utf-8"))


@lru_cache
def load_upload_limits() -> dict:
    return yaml.safe_load((CONFIG_DIR / "uploads.yaml").read_text(encoding="utf-8"))


@lru_cache
def load_image_processing_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "image_processing.yaml").read_text(encoding="utf-8"))


@lru_cache
def load_rules() -> dict:
    return yaml.safe_load((CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8"))


@lru_cache
def load_cpwd_rates() -> dict:
    return json.loads((CONFIG_DIR / "cpwd_rates.json").read_text(encoding="utf-8"))


def get_rule(rule_id: str) -> dict:
    """Return one rule (or the fallback) from rules.yaml by its id."""
    rules = load_rules()
    for rule in rules["rules"]:
        if rule["id"] == rule_id:
            return rule
    if rules["fallback"]["id"] == rule_id:
        return rules["fallback"]
    raise KeyError(f"No rule called {rule_id!r} in config/rules.yaml")
