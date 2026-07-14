import os
from pathlib import Path

import yaml

from src.core.models import (
    AggregationConfig,
    AppConfig,
    DetectionConfig,
    PipelineConfig,
    SamplingConfig,
    StorageConfig,
    VideoConfig,
    WebConfig,
)


def load_config(yaml_path: str | Path) -> AppConfig:
    yaml_path = Path(yaml_path)
    data: dict = {}
    if yaml_path.exists():
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

    def _section(name: str) -> dict:
        return data.get(name, {})

    sampling_raw = _section("sampling")
    detection_raw = _section("detection")
    aggregation_raw = _section("aggregation")
    pipeline_raw = _section("pipeline")
    video_raw = _section("video")
    storage_raw = _section("storage")
    web_raw = _section("web")

    # Env overrides: SURVEILLANCE_SAMPLING__FPS -> sampling.fps
    prefix = "SURVEILLANCE_"
    for key, val in os.environ.items():
        if key.startswith(prefix) and "__" in key[len(prefix) :]:
            parts = key[len(prefix) :].lower().split("__", 1)
            section_name, field_name = parts[0], parts[1]
            section_map = {
                "sampling": sampling_raw,
                "detection": detection_raw,
                "aggregation": aggregation_raw,
                "pipeline": pipeline_raw,
                "video": video_raw,
                "storage": storage_raw,
                "web": web_raw,
            }
            if section_name in section_map:
                # Try to parse as number
                try:
                    val = float(val)
                    if val == int(val):
                        val = int(val)
                except ValueError:
                    pass
                section_map[section_name][field_name] = val

    return AppConfig(
        video=VideoConfig(**video_raw) if video_raw else VideoConfig(),
        sampling=SamplingConfig(**sampling_raw) if sampling_raw else SamplingConfig(),
        detection=DetectionConfig(**detection_raw) if detection_raw else DetectionConfig(),
        aggregation=(
            AggregationConfig(**aggregation_raw) if aggregation_raw else AggregationConfig()
        ),
        pipeline=PipelineConfig(**pipeline_raw) if pipeline_raw else PipelineConfig(),
        storage=StorageConfig(**storage_raw) if storage_raw else StorageConfig(),
        web=WebConfig(**web_raw) if web_raw else WebConfig(),
    )
