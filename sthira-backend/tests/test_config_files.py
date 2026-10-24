"""Checks that the config files are valid and hold the numbers from the deck."""
import json
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config"


def load_yaml(name):
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def test_thresholds_match_the_deck():
    t = load_yaml("thresholds.yaml")
    assert t["marker"]["aruco_size_mm"] == 50
    assert t["marker"]["id_card_width_mm"] == 85.6
    assert t["audio"]["highpass_hz"] == 600
    assert t["audio"]["window_ms"] == 50
    assert t["audio"]["void_below_hz"] == 900
    assert t["audio"]["solid_above_hz"] == 1400
    assert (t["crack"]["shear_angle_min_deg"], t["crack"]["shear_angle_max_deg"]) == (30, 60)
    assert t["is456_crack_limit_mm"] == {"mild": 0.3, "moderate": 0.2, "severe": 0.1}


def _lookup(t, dotted):
    node = t
    for part in dotted.split("."):
        node = node[part]
    return node


def test_every_rule_threshold_name_exists():
    t = load_yaml("thresholds.yaml")
    rules = load_yaml("rules.yaml")["rules"]
    assert [r["id"] for r in rules] == [
        "shear_risk", "void_risk", "plaster_spalling", "minor", "hairline"]
    for rule in rules:
        assert 1 <= rule["severity"] <= 5
        for cond in rule["when"]:
            for key in ("value", "low", "high"):
                if key in cond:
                    _lookup(t, cond[key])  # raises KeyError if the name is wrong


def test_cpwd_rates_are_marked_placeholder():
    data = json.loads((CONFIG / "cpwd_rates.json").read_text(encoding="utf-8"))
    assert data["is_placeholder"] is True
    assert len(data["items"]) == 3
    assert all(i["is_placeholder"] for i in data["items"])
