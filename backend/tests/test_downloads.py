import base64

from fastapi.testclient import TestClient

from backend.qbittorrent import magnet_hash, normalize_hash, public_state


def test_magnet_hash_accepts_hex_and_base32():
    raw = bytes.fromhex("0123456789abcdef0123456789abcdef01234567")
    base32 = base64.b32encode(raw).decode()
    expected = raw.hex()
    assert magnet_hash(f"magnet:?xt=urn:btih:{expected.upper()}&dn=test") == expected
    assert magnet_hash(f"magnet:?xt=urn:btih:{base32}") == expected


def test_hash_and_state_validation():
    assert normalize_hash("a" * 40) == "a" * 40
    assert public_state("stalledDL", .5) == "downloading"
    assert public_state("stoppedDL", .5) == "paused"
    assert public_state("uploading", 1) == "completed"
    try:
        normalize_hash("../../bad")
        assert False
    except ValueError:
        pass


def test_download_routes_map_client_and_conflicts(tmp_path, monkeypatch):
    import backend.database as database
    import backend.main as main

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    sample_hash = "1" * 40

    class FakeClient:
        def close(self): pass
        def status(self): return {"connected": True, "version": "test", "download_speed": 1, "upload_speed": 2, "error": None}
        def torrents(self): return [{"hash": sample_hash, "name": "demo", "status": "paused", "progress": .5}]
        def add(self, magnet): return magnet_hash(magnet)
        def action(self, info_hash, action, delete_files=False):
            assert info_hash == sample_hash

    monkeypatch.setattr(main, "QBitClient", FakeClient)
    with TestClient(main.app) as client:
        assert client.get("/api/downloads/status").json()["connected"] is True
        assert client.get("/api/downloads").json()[0]["name"] == "demo"
        result = client.post("/api/downloads", json={"magnet": f"magnet:?xt=urn:btih:{sample_hash}"})
        assert result.status_code == 202 and result.json()["hash"] == sample_hash
        assert client.post(f"/api/downloads/{sample_hash}/pause").status_code == 204
        assert client.request("DELETE", f"/api/downloads/{sample_hash}", json={"delete_files": False}).status_code == 204
