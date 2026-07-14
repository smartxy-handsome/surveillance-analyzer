from src.utils.time_format import seconds_to_hms, hms_to_seconds


def test_seconds_to_hms_zero():
    assert seconds_to_hms(0) == "00:00:00"


def test_seconds_to_hms_simple():
    assert seconds_to_hms(61) == "00:01:01"


def test_seconds_to_hms_with_millis():
    assert seconds_to_hms(3661.5) == "01:01:01"


def test_seconds_to_hms_large():
    assert seconds_to_hms(86399) == "23:59:59"


def test_hms_to_seconds_simple():
    assert hms_to_seconds("00:01:01") == 61.0


def test_hms_to_seconds_zero():
    assert hms_to_seconds("00:00:00") == 0.0


def test_roundtrip():
    original = 3723.7
    assert hms_to_seconds(seconds_to_hms(original)) == int(original)
