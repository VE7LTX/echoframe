from echoframe.models import Segment
from echoframe.renderer import render_note


def test_render_note_includes_frontmatter():
    segments = [Segment(start=0.0, end=1.0, text="Hello")]
    note = render_note(
        title="Test",
        date="2026-01-13",
        audio_filename="test.wav",
        segments=segments,
        participants=["Matt"],
        tags=["research"],
        duration_seconds=10,
        device="Zoom H2",
        sample_rate_hz=44100,
        bit_depth=16,
        channels=4,
    )
    assert "title: Test" in note
    assert "audio: test.wav" in note
    assert "participants:" in note
    assert "tags:" in note
    assert "channels: 4" in note
    assert "## Transcript" in note
