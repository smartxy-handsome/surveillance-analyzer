def seconds_to_hms(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def hms_to_seconds(hms: str) -> float:
    parts = hms.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
