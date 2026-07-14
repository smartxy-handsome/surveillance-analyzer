import os
import yaml
import pytest
from pathlib import Path
from src.core.config import load_config


def test_load_default_config(tmp_path):
    config = load_config(tmp_path / "nonexistent.yaml")
    assert config.sampling.fps == 3.0
    assert config.detection.confidence_threshold == 0.5
    assert config.detection.device == "cuda:0"


def test_load_custom_yaml(tmp_path):
    cfg = {"sampling": {"fps": 5.0}, "detection": {"confidence_threshold": 0.7}}
    p = tmp_path / "custom.yaml"
    p.write_text(yaml.dump(cfg))
    config = load_config(p)
    assert config.sampling.fps == 5.0
    assert config.detection.confidence_threshold == 0.7
    # Unset values fall back to defaults
    assert config.detection.device == "cuda:0"


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SURVEILLANCE_SAMPLING__FPS", "10.0")
    config = load_config(tmp_path / "nonexistent.yaml")
    assert config.sampling.fps == 10.0
