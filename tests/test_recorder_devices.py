from echoframe.recorder import (
    select_preferred_device,
    find_zoom_name_from_candidates,
)


def test_select_preferred_device_prefers_name():
    candidates = [
        {"name": "Built-in Mic", "index": 1},
        {"name": "ZOOM H2 Handy Recorder", "index": 2},
    ]
    result = select_preferred_device(candidates, prefer_name="zoom h2")
    assert result["name"] == "ZOOM H2 Handy Recorder"


def test_select_preferred_device_falls_back_to_zoom():
    candidates = [
        {"name": "Built-in Mic", "index": 1},
        {"name": "Zoom H4", "index": 2},
    ]
    result = select_preferred_device(candidates, prefer_name=None)
    assert result["name"] == "Zoom H4"


def test_find_zoom_name_from_candidates():
    candidates = [
        {"name": "USB Mic", "index": 1},
        {"name": "ZOOM Recording Mixer (ZOOM H Series Audio)", "index": 2},
    ]
    assert (
        find_zoom_name_from_candidates(candidates)
        == "ZOOM Recording Mixer (ZOOM H Series Audio)"
    )
