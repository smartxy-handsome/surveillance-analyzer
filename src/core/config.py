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

# Root of runtime artifacts (results.db, videos/, captures/). Kept as a single
# constant so every component derives its path from the same place.
DATA_DIR = Path("data")


def load_config(yaml_path: str | Path) -> AppConfig:
    yaml_path = Path(yaml_path)
    data: dict = {}
    if yaml_path.exists():
        # Config files are UTF-8 by convention; the locale default would be
        # GBK on Chinese-locale Windows and choke on UTF-8 comments.
        with open(yaml_path, encoding="utf-8") as f:
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

    sampling = SamplingConfig(**sampling_raw) if sampling_raw else SamplingConfig()
    # 'uniform' is the only implemented strategy; reject anything else loudly
    # instead of silently analysing with unintended behaviour.
    if sampling.strategy != "uniform":
        raise ValueError(f"Unsupported sampling strategy: {sampling.strategy!r} (only 'uniform')")

    pipeline = PipelineConfig(**pipeline_raw) if pipeline_raw else PipelineConfig()
    # Parallel decode threads deliver frames out of order, which corrupts the
    # aggregator's gap logic (it assumes chronological arrival). Until the
    # pipeline gains a reordering buffer, 1 is the only correct value.
    if pipeline.num_decode_threads != 1:
        raise ValueError(
            f"pipeline.num_decode_threads must be 1 (got {pipeline.num_decode_threads}): "
            "parallel decoding breaks chronological aggregation"
        )

    web = WebConfig(**web_raw) if web_raw else WebConfig()
    # An enabled guard with a blank key would reject every request including
    # the operator's; catch the misconfiguration at startup instead.
    if web.auth_enabled and not web.auth_api_key:
        raise ValueError("web.auth_enabled requires a non-empty web.auth_api_key")

    return AppConfig(
        video=VideoConfig(**video_raw) if video_raw else VideoConfig(),
        sampling=sampling,
        detection=DetectionConfig(**detection_raw) if detection_raw else DetectionConfig(),
        aggregation=(
            AggregationConfig(**aggregation_raw) if aggregation_raw else AggregationConfig()
        ),
        pipeline=pipeline,
        storage=StorageConfig(**storage_raw) if storage_raw else StorageConfig(),
        web=web,
    )
