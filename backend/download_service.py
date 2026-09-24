import threading
from pathlib import PurePosixPath

from .database import connect
from .media_service import MEDIA_EXTENSIONS, start_scan, utcnow
from .qbittorrent import QBitClient, QBitError

_stop = threading.Event()
_thread = None


def reconcile(client: QBitClient) -> None:
    completed = [item for item in client.torrents() if item["status"] == "completed"]
    needs_scan = False
    with connect() as db:
        for torrent in completed:
            for item in client.files(torrent["hash"]):
                relative = PurePosixPath(item.get("name", "")).as_posix().lstrip("/")
                if (not relative or ".." in PurePosixPath(relative).parts
                        or PurePosixPath(relative).suffix.lower() not in MEDIA_EXTENSIONS):
                    continue
                media = db.execute("SELECT id FROM media WHERE kind='local' AND library_id='downloads' AND location=?", (relative,)).fetchone()
                db.execute("""INSERT INTO download_imports(torrent_hash,relative_path,media_id,status,imported_at,updated_at)
                    VALUES(?,?,? ,?,CASE WHEN ? IS NOT NULL THEN ? END,?)
                    ON CONFLICT(torrent_hash,relative_path) DO UPDATE SET media_id=excluded.media_id,status=excluded.status,
                    imported_at=COALESCE(download_imports.imported_at,excluded.imported_at),updated_at=excluded.updated_at""",
                           (torrent["hash"], relative, media[0] if media else None, "imported" if media else "pending",
                            media[0] if media else None, utcnow(), utcnow()))
                needs_scan |= media is None
    if needs_scan:
        with connect() as db:
            active = db.execute("SELECT 1 FROM scan_jobs WHERE status IN ('pending','scanning','probing','thumbnailing') LIMIT 1").fetchone()
        if not active:
            start_scan()


def _worker():
    client = QBitClient()
    delay = 3
    try:
        while not _stop.wait(delay):
            try:
                reconcile(client)
                delay = 3
            except QBitError:
                delay = min(delay * 2, 60)
    finally:
        client.close()


def start_monitor():
    global _thread
    _stop.clear()
    if not _thread or not _thread.is_alive():
        _thread = threading.Thread(target=_worker, daemon=True, name="qbt-monitor")
        _thread.start()


def stop_monitor():
    _stop.set()
    if _thread:
        _thread.join(timeout=2)
