from echoframe.storage import timestamp_slug, build_session_basename


def test_timestamp_slug_format():
    slug = timestamp_slug()
    assert len(slug) == 10
    assert slug.count("-") == 2


def test_build_session_basename():
    name = build_session_basename("Client Interview")
    assert "--" in name
    assert "Client-Interview" in name
