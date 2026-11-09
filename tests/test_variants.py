import pytest
from fastapi.testclient import TestClient

import app as app_module
import settings
import variants
from app import create_app
from conftest import make_engine
from options import SETTINGS
from tokens import TokenStore

ADMIN = {"X-Internal-Token": "admin"}


def hw(ram=16000):
    return {"cpu_cores": 8, "ram_total_mb": 32000, "ram_available_mb": ram, "gpu": None}


def get(rows_, key):
    return variants.find(rows_, key)


def test_both_formats_are_listed_smallest_first_and_share_the_download_state():
    result = variants.listing(hw(), "bfloat16", True)
    assert [r["id"] for r in result] == ["bfloat16", "float32"]
    assert all(r["downloaded"] for r in result) and all("CPU" in r["title"] for r in result)


def test_a_format_that_does_not_fit_is_refused_with_the_numbers():
    result = variants.listing(hw(ram=6000), "bfloat16", False)
    assert get(result, "float32")["fits"] is False and "6000 MB" in get(result, "float32")["reason"]
    assert get(result, "bfloat16")["fits"] is True


def test_unreadable_memory_claims_nothing_and_the_format_in_use_always_fits():
    assert get(variants.listing(hw(ram=None), "bfloat16", False), "float32")["fits"] is None
    result = variants.listing(hw(ram=10), "float32", False)
    assert get(result, "float32")["fits"] is True and get(result, "float32")["current"] is True


def build(tmp_path, monkeypatch, dtype, on_disk=True):
    # 6000 MB free: bfloat16 (about 5000 MB) fits, float32 (about 8000 MB) does not.
    monkeypatch.setattr(app_module.hardware, "probe", lambda: hw(ram=6000))
    store = TokenStore(tmp_path / "t.json")
    config = settings.Config(store.settings_path, SETTINGS)
    config.set({"update_check_hours": 0, "warm": False})
    engine = make_engine(dtype=dtype, cached_sha=lambda _: "abc" if on_disk else None)
    return TestClient(create_app(engine, "admin", tokens=store, config=config)), config


def test_variants_endpoint_is_admin_only_and_marks_the_weights(tmp_path, monkeypatch):
    client, _ = build(tmp_path, monkeypatch, "bfloat16", on_disk=False)
    assert client.get("/admin/variants").status_code == 401
    body = client.get("/admin/variants", headers=ADMIN).json()
    assert "6000 MB" in body["summary"] and "not measured" in body["estimate"]
    assert [r["id"] for r in body["variants"] if r["current"]] == ["bfloat16"]
    assert not any(r["downloaded"] for r in body["variants"])


def test_choosing_a_format_saves_the_dtype(tmp_path, monkeypatch):
    client, config = build(tmp_path, monkeypatch, "float32")
    reply = client.put("/admin/variant", json={"id": "bfloat16"}, headers=ADMIN)
    assert reply.status_code == 200 and reply.json()["restart_required"] is True
    assert config.get("dtype") == "bfloat16"


def test_choosing_one_that_does_not_fit_is_refused_and_saves_nothing(tmp_path, monkeypatch):
    client, config = build(tmp_path, monkeypatch, "bfloat16")
    before = config.get("dtype")
    reply = client.put("/admin/variant", json={"id": "float32"}, headers=ADMIN)
    assert reply.status_code == 409 and "6000 MB" in reply.json()["detail"]
    assert config.get("dtype") == before
    assert client.put("/admin/variant", json={"id": "nope"}, headers=ADMIN).status_code == 404
