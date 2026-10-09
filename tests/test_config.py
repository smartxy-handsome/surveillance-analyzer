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


def test_pipeline_max_concurrent_jobs_default():
    config = load_config(Path("config/default.yaml"))
    assert config.pipeline.max_concurrent_jobs == 1


def test_pipeline_max_concurrent_jobs_from_yaml(tmp_path):
    cfg = {"pipeline": {"max_concurrent_jobs": 3}}
    p = tmp_path / "custom.yaml"
    p.write_text(yaml.dump(cfg))
    config = load_config(p)
    assert config.pipeline.max_concurrent_jobs == 3


def test_web_defaults_to_loopback():
    """Unauthenticated API must not bind a public interface by default."""
    config = load_config(Path("config/default.yaml"))
    assert config.web.host == "127.0.0.1"


def test_reject_unknown_sampling_strategy(tmp_path):
    cfg = {"sampling": {"fps": 3.0, "strategy": "random"}}
    p = tmp_path / "custom.yaml"
    p.write_text(yaml.dump(cfg))
    with pytest.raises(ValueError, match="sampling strategy"):
        load_config(p)


def test_reject_parallel_decode_threads(tmp_path):
    """Only 1 decode thread aggregates chronologically; >1 must fail loudly."""
    cfg = {"pipeline": {"num_decode_threads": 2}}
    p = tmp_path / "custom.yaml"
    p.write_text(yaml.dump(cfg))
    with pytest.raises(ValueError, match="num_decode_threads"):
        load_config(p)
