"""Blueprints parse and only use inputs they declare."""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

BLUEPRINTS = sorted((Path(__file__).resolve().parents[1] / "blueprints").rglob("*.yaml"))


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: f"<input:{loader.construct_scalar(node)}>")


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_blueprint(path):
    text = path.read_text(encoding="utf-8")
    data = yaml.load(text, Loader=Loader)
    meta = data["blueprint"]
    assert meta["domain"] == "automation"
    assert meta["source_url"].endswith(f"/blueprints/automation/pixel_clock/{path.name}")
    used = set(re.findall(r"!input (\w+)", text))
    assert used <= set(meta["input"]), used - set(meta["input"])
    assert data["triggers"] and data["actions"]
