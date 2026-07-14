import pytest
from src.video.sampler import compute_frame_indices


def test_uniform_sampling_basic():
    # video at 30fps, sample at 3fps -> every 10th frame
    indices = compute_frame_indices(video_fps=30.0, target_fps=3.0, total_frames=300)
    assert indices == list(range(0, 300, 10))


def test_uniform_sampling_exact_divide():
    indices = compute_frame_indices(video_fps=25.0, target_fps=5.0, total_frames=50)
    assert indices == list(range(0, 50, 5))


def test_target_fps_higher_than_video():
    # If target fps >= video fps, sample every frame
    indices = compute_frame_indices(video_fps=25.0, target_fps=30.0, total_frames=50)
    assert indices == list(range(0, 50))


def test_single_frame():
    indices = compute_frame_indices(video_fps=30.0, target_fps=3.0, total_frames=1)
    assert indices == [0]


def test_empty_video():
    indices = compute_frame_indices(video_fps=30.0, target_fps=3.0, total_frames=0)
    assert indices == []


def test_target_fps_zero():
    with pytest.raises(ValueError):
        compute_frame_indices(video_fps=30.0, target_fps=0, total_frames=100)


def test_video_fps_zero():
    with pytest.raises(ValueError):
        compute_frame_indices(video_fps=0, target_fps=3.0, total_frames=100)
