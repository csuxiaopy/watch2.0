import json
import math
import mimetypes
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .database import connect, init_database
from .media_service import THUMBNAIL_ROOT, safe_media_path, start_scan, sync_libraries, utcnow
from .download_service import start_monitor, stop_monitor
from .qbittorrent import QBitClient, QBitError, normalize_hash
from .schemas import (CollectionItems, Layout, MediaItem, MediaPage, MediaUpdate,
                      NameCreate, ProgressUpdate, SourceCreate, TagBatch, WatchlistOrder,
                      MagnetCreate, DownloadDelete)

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    sync_libraries()
    THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)
    start_monitor()
    yield
    stop_monitor()


app = FastAPI(title="Watch 2.0", lifespan=lifespan)


def serialize_media(row, db=None) -> MediaItem:
    tags = []
    if db:
        tags = [dict(x) for x in db.execute("""SELECT t.id,t.name FROM tags t JOIN media_tags mt ON mt.tag_id=t.id
            WHERE mt.media_id=? ORDER BY t.name COLLATE NOCASE""", (row["id"],)).fetchall()]
    thumb = f"/api/thumbnails/{row['id']}" if row["thumbnail_path"] else None
    return MediaItem(
        id=row["id"], name=row["name"], kind=row["kind"], location=row["location"],
        available=bool(row["available"]), playback_url=f"/api/files/{row['id']}" if row["kind"] == "local" else row["location"],
        library_id=row["library_id"], original_name=row["original_name"], file_size=row["file_size"],
        file_mtime=row["file_mtime"], duration=row["duration"], width=row["width"], height=row["height"],
        video_codec=row["video_codec"], audio_codec=row["audio_codec"], imported_at=row["imported_at"],
        last_scanned_at=row["last_scanned_at"], favorite=bool(row["favorite"]), rating=row["rating"],
        notes=row["notes"], watch_count=row["watch_count"], last_watched_at=row["last_watched_at"],
        playback_position=row["playback_position"], completed=bool(row["completed"]),
        thumbnail_status=row["thumbnail_status"], thumbnail_url=thumb, tags=tags)


def require_media(item_id: str, db):
    row = db.execute("SELECT * FROM media WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "视频不存在")
    return row


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _qbt_call(callback):
    client = QBitClient()
    try:
        return callback(client)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QBitError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        client.close()


@app.get("/api/downloads/status")
def download_status():
    try:
        return _qbt_call(lambda client: client.status())
    except HTTPException as exc:
        return {"connected": False, "version": None, "download_speed": 0, "upload_speed": 0, "error": exc.detail}


@app.get("/api/downloads")
def list_downloads():
    def load(client):
        rows = client.torrents()
        with connect() as db:
            for row in rows:
                imported = db.execute("""SELECT di.media_id,m.name FROM download_imports di LEFT JOIN media m ON m.id=di.media_id
                    WHERE di.torrent_hash=? AND di.media_id IS NOT NULL ORDER BY di.relative_path""", (row["hash"],)).fetchall()
                row["imported_media"] = [dict(item) for item in imported]
        return rows
    return _qbt_call(load)


@app.post("/api/downloads", status_code=202)
def add_download(payload: MagnetCreate):
    return {"hash": _qbt_call(lambda client: client.add(payload.magnet))}


@app.post("/api/downloads/{info_hash}/pause", status_code=204)
def pause_download(info_hash: str):
    _qbt_call(lambda client: client.action(normalize_hash(info_hash), "pause"))


@app.post("/api/downloads/{info_hash}/resume", status_code=204)
def resume_download(info_hash: str):
    _qbt_call(lambda client: client.action(normalize_hash(info_hash), "resume"))


@app.delete("/api/downloads/{info_hash}", status_code=204)
def delete_download(info_hash: str, payload: DownloadDelete):
    _qbt_call(lambda client: client.action(normalize_hash(info_hash), "delete", payload.delete_files))


@app.get("/api/media", response_model=list[MediaItem])
def get_wall_media():
    with connect() as db:
        rows = db.execute("SELECT * FROM media ORDER BY available DESC, name COLLATE NOCASE").fetchall()
        return [serialize_media(row, db) for row in rows]


@app.get("/api/library/media", response_model=MediaPage)
def get_library_media(
    page: int = Query(1, ge=1), page_size: int = Query(48, ge=1, le=100), query: str = "",
    tag_id: str | None = None, collection_id: str | None = None, favorite: bool | None = None,
    completed: bool | None = None, available: bool | None = None, library_id: str | None = None,
    sort: str = "imported_desc",
):
    where, params = ["1=1"], []
    if query:
        where.append("(m.name LIKE ? OR m.original_name LIKE ? OR m.location LIKE ? OR m.notes LIKE ?)")
        params.extend([f"%{query}%"] * 4)
    for field, value in (("favorite", favorite), ("completed", completed), ("available", available)):
        if value is not None:
            where.append(f"m.{field}=?")
            params.append(int(value))
    if library_id:
        where.append("m.library_id=?"); params.append(library_id)
    if tag_id:
        where.append("EXISTS(SELECT 1 FROM media_tags mt WHERE mt.media_id=m.id AND mt.tag_id=?)"); params.append(tag_id)
    if collection_id:
        where.append("EXISTS(SELECT 1 FROM collection_items ci WHERE ci.media_id=m.id AND ci.collection_id=?)"); params.append(collection_id)
    orders = {"name_asc": "m.name COLLATE NOCASE ASC", "name_desc": "m.name COLLATE NOCASE DESC",
              "imported_asc": "m.imported_at ASC", "imported_desc": "m.imported_at DESC",
              "modified_desc": "m.file_mtime DESC", "duration_desc": "m.duration DESC", "size_desc": "m.file_size DESC"}
    order = orders.get(sort)
    if not order:
        raise HTTPException(400, "不支持的排序方式")
    clause = " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT count(*) FROM media m WHERE {clause}", params).fetchone()[0]
        rows = db.execute(f"SELECT m.* FROM media m WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                          (*params, page_size, (page - 1) * page_size)).fetchall()
        return MediaPage(items=[serialize_media(row, db) for row in rows], page=page, page_size=page_size,
                         total=total, pages=max(1, math.ceil(total / page_size)))


@app.get("/api/library/media/{item_id}", response_model=MediaItem)
def get_media_detail(item_id: str):
    with connect() as db:
        return serialize_media(require_media(item_id, db), db)


@app.patch("/api/library/media/{item_id}", response_model=MediaItem)
def update_media(item_id: str, payload: MediaUpdate):
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "没有要更新的字段")
    if "name" in values:
        values["custom_title"] = 1
    with connect() as db:
        require_media(item_id, db)
        db.execute(f"UPDATE media SET {','.join(f'{k}=?' for k in values)} WHERE id=?", (*values.values(), item_id))
        return serialize_media(require_media(item_id, db), db)


@app.put("/api/library/media/{item_id}/progress")
def save_progress(item_id: str, payload: ProgressUpdate):
    completed = payload.completed if payload.completed is not None else bool(payload.duration and payload.duration > 0 and payload.position >= payload.duration - 15)
    with connect() as db:
        require_media(item_id, db)
        db.execute("""UPDATE media SET playback_position=?,completed=?,last_watched_at=?,
            watch_count=watch_count+CASE WHEN playback_position=0 AND ? > 0 THEN 1 ELSE 0 END WHERE id=?""",
                   (payload.position, int(completed), utcnow(), payload.position, item_id))
    return {"ok": True, "completed": completed}


@app.post("/api/media/scan", status_code=202)
def rescan_media():
    return {"job_id": start_scan()}


@app.get("/api/media/scan/{job_id}")
def scan_status(job_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM scan_jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "扫描任务不存在")
    return dict(row)


@app.get("/api/tags")
def list_tags():
    with connect() as db:
        return [dict(x) for x in db.execute("""SELECT t.id,t.name,count(mt.media_id) count FROM tags t
            LEFT JOIN media_tags mt ON mt.tag_id=t.id GROUP BY t.id ORDER BY t.name COLLATE NOCASE""").fetchall()]


@app.post("/api/tags", status_code=201)
def create_tag(payload: NameCreate):
    item_id = str(uuid.uuid4())
    try:
        with connect() as db:
            db.execute("INSERT INTO tags(id,name) VALUES(?,?)", (item_id, payload.name.strip()))
    except Exception as exc:
        raise HTTPException(409, "标签名称已存在") from exc
    return {"id": item_id, "name": payload.name.strip(), "count": 0}


@app.put("/api/tags/{item_id}")
def rename_tag(item_id: str, payload: NameCreate):
    with connect() as db:
        if db.execute("UPDATE tags SET name=? WHERE id=?", (payload.name.strip(), item_id)).rowcount == 0:
            raise HTTPException(404, "标签不存在")
    return {"id": item_id, "name": payload.name.strip()}


@app.delete("/api/tags/{item_id}", status_code=204)
def delete_tag(item_id: str):
    with connect() as db:
        db.execute("DELETE FROM tags WHERE id=?", (item_id,))
    return Response(status_code=204)


@app.post("/api/tags/batch")
def batch_tags(payload: TagBatch):
    with connect() as db:
        for media_id in payload.media_ids:
            require_media(media_id, db)
            for tag_id in payload.tag_ids:
                if payload.action == "add":
                    db.execute("INSERT OR IGNORE INTO media_tags(media_id,tag_id) VALUES(?,?)", (media_id, tag_id))
                else:
                    db.execute("DELETE FROM media_tags WHERE media_id=? AND tag_id=?", (media_id, tag_id))
    return {"updated": len(payload.media_ids)}


@app.get("/api/collections")
def list_collections():
    with connect() as db:
        return [dict(x) for x in db.execute("""SELECT c.id,c.name,count(ci.media_id) count FROM collections c
            LEFT JOIN collection_items ci ON ci.collection_id=c.id GROUP BY c.id ORDER BY c.name COLLATE NOCASE""").fetchall()]


@app.post("/api/collections", status_code=201)
def create_collection(payload: NameCreate):
    item_id = str(uuid.uuid4())
    try:
        with connect() as db:
            db.execute("INSERT INTO collections(id,name) VALUES(?,?)", (item_id, payload.name.strip()))
    except Exception as exc:
        raise HTTPException(409, "合集名称已存在") from exc
    return {"id": item_id, "name": payload.name.strip(), "count": 0}


@app.put("/api/collections/{item_id}")
def rename_collection(item_id: str, payload: NameCreate):
    with connect() as db:
        if db.execute("UPDATE collections SET name=? WHERE id=?", (payload.name.strip(), item_id)).rowcount == 0:
            raise HTTPException(404, "合集不存在")
    return {"id": item_id, "name": payload.name.strip()}


@app.delete("/api/collections/{item_id}", status_code=204)
def delete_collection(item_id: str):
    with connect() as db:
        db.execute("DELETE FROM collections WHERE id=?", (item_id,))
    return Response(status_code=204)


@app.put("/api/collections/{item_id}/items")
def set_collection_items(item_id: str, payload: CollectionItems):
    with connect() as db:
        if not db.execute("SELECT 1 FROM collections WHERE id=?", (item_id,)).fetchone():
            raise HTTPException(404, "合集不存在")
        db.execute("DELETE FROM collection_items WHERE collection_id=?", (item_id,))
        for position, media_id in enumerate(payload.media_ids):
            require_media(media_id, db)
            db.execute("INSERT INTO collection_items(collection_id,media_id,position) VALUES(?,?,?)",
                       (item_id, media_id, position))
    return {"updated": len(payload.media_ids)}


@app.get("/api/watchlist", response_model=list[MediaItem])
def get_watchlist():
    with connect() as db:
        rows = db.execute("""SELECT m.* FROM watchlist_items w
            JOIN media m ON m.id=w.media_id ORDER BY w.position""").fetchall()
        return [serialize_media(row, db) for row in rows]


@app.post("/api/watchlist/{item_id}", response_model=MediaItem)
def add_to_watchlist(item_id: str):
    with connect() as db:
        row = require_media(item_id, db)
        position = db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM watchlist_items").fetchone()[0]
        db.execute("INSERT OR IGNORE INTO watchlist_items(media_id,position) VALUES(?,?)", (item_id, position))
        return serialize_media(row, db)


@app.delete("/api/watchlist/{item_id}", status_code=204)
def remove_from_watchlist(item_id: str):
    with connect() as db:
        db.execute("DELETE FROM watchlist_items WHERE media_id=?", (item_id,))
        rows = db.execute("SELECT media_id FROM watchlist_items ORDER BY position").fetchall()
        for position, row in enumerate(rows):
            db.execute("UPDATE watchlist_items SET position=? WHERE media_id=?", (position, row[0]))
    return Response(status_code=204)


@app.put("/api/watchlist/order", response_model=list[MediaItem])
def reorder_watchlist(payload: WatchlistOrder):
    with connect() as db:
        current = [row[0] for row in db.execute("SELECT media_id FROM watchlist_items ORDER BY position")]
        if set(current) != set(payload.media_ids) or len(current) != len(payload.media_ids):
            raise HTTPException(400, "排序必须包含播放列表中的全部视频且不能包含其他视频")
        # Offset first to avoid the UNIQUE(position) constraint during swaps.
        db.execute("UPDATE watchlist_items SET position=position+1000000")
        for position, media_id in enumerate(payload.media_ids):
            db.execute("UPDATE watchlist_items SET position=? WHERE media_id=?", (position, media_id))
        rows = db.execute("""SELECT m.* FROM watchlist_items w JOIN media m ON m.id=w.media_id
            ORDER BY w.position""").fetchall()
        return [serialize_media(row, db) for row in rows]


@app.post("/api/sources", response_model=MediaItem, status_code=201)
def create_source(source: SourceCreate):
    item_id, location = str(uuid.uuid4()), str(source.location)
    try:
        with connect() as db:
            db.execute("""INSERT INTO media(id,name,kind,location,available,original_name,imported_at,last_scanned_at,
                thumbnail_status) VALUES(?,?,?,?,1,?,?,?,'not_applicable')""",
                       (item_id, source.name.strip(), source.kind, location, source.name.strip(), utcnow(), utcnow()))
            return serialize_media(require_media(item_id, db), db)
    except Exception as exc:
        raise HTTPException(409, "该视频地址已存在") from exc


@app.put("/api/sources/{item_id}", response_model=MediaItem)
def update_source(item_id: str, source: SourceCreate):
    with connect() as db:
        row = require_media(item_id, db)
        if row["kind"] == "local":
            raise HTTPException(400, "本地媒体不能编辑为网络源")
        db.execute("UPDATE media SET name=?,kind=?,location=?,available=1 WHERE id=?",
                   (source.name.strip(), source.kind, str(source.location), item_id))
        return serialize_media(require_media(item_id, db), db)


@app.delete("/api/sources/{item_id}", status_code=204)
def delete_source(item_id: str):
    with connect() as db:
        row = require_media(item_id, db)
        if row["kind"] == "local":
            raise HTTPException(400, "本地媒体不能删除")
        db.execute("DELETE FROM media WHERE id=?", (item_id,))
        layout = json.loads(db.execute("SELECT value FROM settings WHERE key='layout'").fetchone()[0])
        for slot in layout["slots"]:
            if slot["media_id"] == item_id:
                slot.update(media_id=None, playing=False)
        db.execute("UPDATE settings SET value=? WHERE key='layout'", (json.dumps(layout),))
    return Response(status_code=204)


@app.get("/api/layout", response_model=Layout)
def get_layout():
    with connect() as db:
        return json.loads(db.execute("SELECT value FROM settings WHERE key='layout'").fetchone()[0])


@app.put("/api/layout", response_model=Layout)
def save_layout(layout: Layout):
    with connect() as db:
        known = {row[0] for row in db.execute("SELECT id FROM media")}
        if any(slot.media_id and slot.media_id not in known for slot in layout.slots):
            raise HTTPException(400, "布局中包含未知媒体")
        db.execute("UPDATE settings SET value=? WHERE key='layout'", (layout.model_dump_json(),))
    return layout


def resolve_local_file(item_id: str) -> Path:
    with connect() as db:
        row = db.execute("""SELECT m.location,m.available,l.root_path FROM media m
            JOIN libraries l ON l.id=m.library_id WHERE m.id=? AND m.kind='local'""", (item_id,)).fetchone()
    if row is None or not row["available"]:
        raise HTTPException(404, "本地视频不存在")
    try:
        path = safe_media_path(Path(row["root_path"]), row["location"])
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not path.is_file():
        raise HTTPException(404, "本地视频文件已丢失")
    return path


@app.get("/api/thumbnails/{item_id}")
def thumbnail(item_id: str):
    with connect() as db:
        row = db.execute("SELECT thumbnail_path FROM media WHERE id=?", (item_id,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "缩略图不存在")
    path = safe_media_path(THUMBNAIL_ROOT, row[0])
    if not path.is_file():
        raise HTTPException(404, "缩略图不存在")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/files/{item_id}")
def serve_media(item_id: str, request: Request):
    path = resolve_local_file(item_id)
    size = path.stat().st_size
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    header = request.headers.get("range")
    if not header:
        return FileResponse(path, media_type=content_type, headers={"Accept-Ranges": "bytes"})
    try:
        unit, value = header.split("=", 1)
        if unit != "bytes" or "," in value: raise ValueError
        start_text, end_text = value.split("-", 1)
        if not start_text:
            start, end = max(size - int(end_text), 0), size - 1
        else:
            start, end = int(start_text), min(int(end_text) if end_text else size - 1, size - 1)
        if start < 0 or start > end or start >= size: raise ValueError
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def stream():
        with path.open("rb") as video:
            video.seek(start); remaining = end - start + 1
            while remaining:
                chunk = video.read(min(1024 * 1024, remaining))
                if not chunk: break
                remaining -= len(chunk); yield chunk
    return StreamingResponse(stream(), status_code=206, media_type=content_type,
        headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{size}",
                 "Content-Length": str(end - start + 1)})


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
