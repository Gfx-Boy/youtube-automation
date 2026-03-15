"""Model loader utility — loads trained weights from weights/ directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import torch

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_cache: dict[str, object] = {}


def load_torchscript(name: str) -> Optional[torch.jit.ScriptModule]:
    """Load a TorchScript model from weights/<name>.pt"""
    if name in _cache:
        return _cache[name]

    path = get_settings().weights_dir / f"{name}.pt"
    if not path.exists():
        log.warning("Weight file not found: %s (skipping)", path)
        return None

    model = torch.jit.load(str(path), map_location="cpu")
    model.eval()
    _cache[name] = model
    log.info("Loaded model: %s", path.name)
    return model


def load_json_config(name: str) -> dict:
    """Load a JSON config from weights/<name>.json"""
    path = get_settings().weights_dir / f"{name}.json"
    if not path.exists():
        log.warning("Config not found: %s (using defaults)", path)
        return {}
    data = json.loads(path.read_text("utf-8"))
    log.info("Loaded config: %s", path.name)
    return data


def get_thresholds() -> dict:
    return load_json_config("thresholds")


def get_prompt_weights() -> dict:
    return load_json_config("prompt_weights")
