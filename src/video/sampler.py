def compute_frame_indices(video_fps: float, target_fps: float, total_frames: int) -> list[int]:
    if target_fps <= 0:
        raise ValueError("target_fps must be positive")
    if video_fps <= 0:
        raise ValueError("video_fps must be positive")
    if total_frames <= 0:
        return []

    step = max(1, int(video_fps / target_fps))
    return list(range(0, total_frames, step))
