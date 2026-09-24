import importlib, json, sqlite3, time
from pathlib import Path
from fastapi.testclient import TestClient


def make_client(tmp_path: Path, monkeypatch):
    media = tmp_path / "media"; media.mkdir(exist_ok=True)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "app.db")); monkeypatch.setenv("MEDIA_ROOT", str(media))
    monkeypatch.setenv("THUMBNAIL_ROOT", str(tmp_path / "data" / "thumbnails")); monkeypatch.delenv("MEDIA_LIBRARIES", raising=False)
    import backend.database as database
    import backend.media_service as media_service
    import backend.main as main
    importlib.reload(database); importlib.reload(media_service)
    media_service.probe = lambda _: {"duration": 120.0, "width": 1920, "height": 1080, "video_codec": "h264", "audio_codec": "aac"}
    media_service.make_thumbnail = lambda *_: ("failed", None)
    importlib.reload(main)
    return TestClient(main.app), media, database, media_service


def scan(client: TestClient):
    response = client.post("/api/media/scan"); assert response.status_code == 202
    job_id = response.json()["job_id"]
    for _ in range(200):
        job = client.get(f"/api/media/scan/{job_id}").json()
        if job["status"] in {"completed", "failed"}: return job
        time.sleep(.01)
    raise AssertionError("scan did not finish")


def test_scan_metadata_layout_and_range(tmp_path, monkeypatch):
    client, media, _, _ = make_client(tmp_path, monkeypatch)
    sample = media / "folder" / "sample.mp4"; sample.parent.mkdir(); sample.write_bytes(b"0123456789")
    with client:
        job = scan(client); assert job["status"] == "completed" and job["total"] == 1
        item = client.get("/api/media").json()[0]
        assert item["location"] == "folder/sample.mp4" and item["duration"] == 120 and item["width"] == 1920
        response = client.get(item["playback_url"], headers={"Range": "bytes=2-5"})
        assert response.status_code == 206 and response.content == b"2345"
        assert client.get(item["playback_url"], headers={"Range": "bytes=99-100"}).status_code == 416
        assert len(client.get("/api/layout").json()["slots"]) == 13


def test_incremental_rename_missing_and_restore(tmp_path, monkeypatch):
    client, media, _, service = make_client(tmp_path, monkeypatch)
    source = media / "old.mp4"; source.write_bytes(b"same-video"); calls = 0
    def counted_probe(_):
        nonlocal calls; calls += 1
        return {"duration": 1, "width": 1, "height": 1, "video_codec": "x", "audio_codec": "y"}
    service.probe = counted_probe
    with client:
        scan(client); original = client.get("/api/media").json()[0]; assert calls == 1
        scan(client); assert calls == 1
        source.rename(media / "renamed.mp4"); scan(client); renamed = client.get("/api/media").json()[0]
        assert renamed["id"] == original["id"] and renamed["location"] == "renamed.mp4"
        (media / "renamed.mp4").unlink(); scan(client); assert client.get("/api/media").json()[0]["available"] is False
        (media / "restored.mp4").write_bytes(b"same-video"); scan(client); restored = client.get("/api/media").json()[0]
        assert restored["id"] == original["id"] and restored["available"] is True


def test_library_filters_tags_collections_and_progress(tmp_path, monkeypatch):
    client, media, _, _ = make_client(tmp_path, monkeypatch)
    (media / "课程一.mp4").write_bytes(b"a"); (media / "电影.mp4").write_bytes(b"b")
    with client:
        scan(client); result = client.get("/api/library/media", params={"page_size": 1, "query": "课程"}).json()
        assert result["total"] == 1 and len(result["items"]) == 1; item_id = result["items"][0]["id"]
        updated = client.patch(f"/api/library/media/{item_id}", json={"name": "Python 课程", "favorite": True, "rating": 5}).json()
        assert updated["favorite"] is True and updated["rating"] == 5
        tag = client.post("/api/tags", json={"name": "学习"}).json()
        assert client.post("/api/tags/batch", json={"media_ids": [item_id], "tag_ids": [tag["id"]], "action": "add"}).status_code == 200
        assert client.get("/api/library/media", params={"tag_id": tag["id"]}).json()["total"] == 1
        collection = client.post("/api/collections", json={"name": "周末"}).json()
        assert client.put(f"/api/collections/{collection['id']}/items", json={"media_ids": [item_id]}).status_code == 200
        assert client.get("/api/library/media", params={"collection_id": collection["id"]}).json()["total"] == 1
        client.put(f"/api/library/media/{item_id}/progress", json={"position": 119, "duration": 120})
        detail = client.get(f"/api/library/media/{item_id}").json()
        assert detail["completed"] is True and detail["playback_position"] == 119
        assert client.delete(f"/api/tags/{tag['id']}").status_code == 204
        assert client.delete(f"/api/collections/{collection['id']}").status_code == 204


def test_remote_source_lifecycle(tmp_path, monkeypatch):
    client, _, _, _ = make_client(tmp_path, monkeypatch)
    with client:
        created = client.post("/api/sources", json={"name": "Demo", "kind": "hls", "location": "https://example.com/live.m3u8"})
        assert created.status_code == 201; item = created.json()
        updated = client.put(f"/api/sources/{item['id']}", json={"name": "Renamed", "kind": "direct", "location": "https://example.com/a.mp4"})
        assert updated.json()["name"] == "Renamed" and client.delete(f"/api/sources/{item['id']}").status_code == 204


def test_watchlist_is_independent_ordered_and_idempotent(tmp_path, monkeypatch):
    client, media, _, _ = make_client(tmp_path, monkeypatch)
    (media / "one.mp4").write_bytes(b"one"); (media / "two.mp4").write_bytes(b"two")
    with client:
        scan(client)
        items = client.get("/api/media").json(); first, second = items[0], items[1]
        assert client.get("/api/watchlist").json() == []
        assert client.post(f"/api/watchlist/{first['id']}").status_code == 200
        assert client.post(f"/api/watchlist/{first['id']}").status_code == 200
        client.post(f"/api/watchlist/{second['id']}")
        assert [x["id"] for x in client.get("/api/watchlist").json()] == [first["id"], second["id"]]
        reordered = client.put("/api/watchlist/order", json={"media_ids": [second["id"], first["id"]]})
        assert [x["id"] for x in reordered.json()] == [second["id"], first["id"]]
        assert client.put("/api/watchlist/order", json={"media_ids": [first["id"]]}).status_code == 400
        assert client.put("/api/watchlist/order", json={"media_ids": [first["id"], first["id"]]}).status_code == 422
        layout = client.get("/api/layout").json(); layout["slots"][0]["media_id"] = first["id"]
        client.put("/api/layout", json=layout)
        assert client.delete(f"/api/watchlist/{first['id']}").status_code == 204
        assert client.get("/api/layout").json()["slots"][0]["media_id"] == first["id"]
        assert client.get(f"/api/library/media/{first['id']}").status_code == 200
        assert [x["id"] for x in client.get("/api/watchlist").json()] == [second["id"]]


def test_safe_path_and_partial_scan_failure(tmp_path, monkeypatch):
    client, media, _, service = make_client(tmp_path, monkeypatch)
    (media / "good.mp4").write_bytes(b"good"); (media / "bad.mp4").write_bytes(b"bad"); original = service.quick_fingerprint
    service.quick_fingerprint = lambda path: (_ for _ in ()).throw(OSError("broken")) if path.name == "bad.mp4" else original(path)
    with client:
        job = scan(client); assert job["status"] == "completed" and job["errors"] == 1
        assert len(client.get("/api/media").json()) == 1
    try:
        service.safe_media_path(media, "../outside.mp4"); raise AssertionError("unsafe path accepted")
    except PermissionError: pass


def test_legacy_migration_preserves_layout(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "app.db"; db_path.parent.mkdir(); db = sqlite3.connect(db_path)
    db.executescript("""CREATE TABLE media(id TEXT PRIMARY KEY,name TEXT,kind TEXT,location TEXT,available INTEGER,UNIQUE(kind,location));
        CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);""")
    old_id = "local_old"; db.execute("INSERT INTO media VALUES(?,?,?,?,1)", (old_id, "old.mp4", "local", "old.mp4"))
    slots = [{"slot_id": i, "position": "main" if i == 0 else f"p{i-1}", "media_id": old_id if i == 0 else None,
              "muted": i != 0, "volume": 1, "playing": False} for i in range(13)]
    db.execute("INSERT INTO settings VALUES('layout',?)", (json.dumps({"slots": slots}),)); db.commit(); db.close()
    monkeypatch.setenv("DATABASE_PATH", str(db_path)); monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media")); (tmp_path / "media").mkdir()
    import backend.database as database
    importlib.reload(database); database.init_database()
    with database.connect() as migrated:
        new_id = migrated.execute("SELECT id FROM media").fetchone()[0]
        layout = json.loads(migrated.execute("SELECT value FROM settings WHERE key='layout'").fetchone()[0])
        assert new_id != old_id and layout["slots"][0]["media_id"] == new_id
        assert migrated.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0] == "4"
        assert migrated.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='download_imports'").fetchone()
