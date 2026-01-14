import os
import tempfile

from echoframe.config import Config, load_config, save_config


def test_save_and_load_config_roundtrip():
    cfg = Config(base_dir="C:/Echo")
    cfg.context["user_name"] = "Matt"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "echoframe_config.yml")
        save_config(path, cfg)
        loaded = load_config(path)

    assert loaded.base_dir == "C:/Echo"
    assert loaded.context.get("user_name") == "Matt"
