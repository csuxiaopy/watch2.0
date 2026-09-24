import hashlib
import json
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .database import connect

MEDIA_EXTENSIONS = {".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v", ".mkv", ".avi", ".flv", ".ts"}
THUMBNAIL_ROOT = Path(os.getenv("THUMBNAIL_ROOT", "/data/thumbnails")).resolve()
FINGERPRINT_CHUNK = 1024 * 1024
_scan_lock = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def configured_libraries() -> list[dict[str, str]]:
    raw = os.getenv("MEDIA_LIBRARIES")
    if raw:
        libraries = [{"id": str(x["id"]), "name": str(x.get("name", x["id"])),
                      "root_path": str(Path(x["path"]).resolve())} for x in json.loads(raw)]
    else:
        libraries = [{"id": "default", "name": "默认媒体库",
                      "root_path": str(Path(os.getenv("MEDIA_ROOT", "media")).resolve())}]
    download_root = os.getenv("DOWNLOAD_MEDIA_ROOT")
    if download_root and not any(item["id"] == "downloads" for item in libraries):
        libraries.append({"id": "downloads", "name": "下载的视频", "root_path": str(Path(download_root).resolve())})
    return libraries


def sync_libraries() -> None:
    with connect() as db:
        for item in configured_libraries():
            db.execute("""INSERT INTO libraries(id,name,root_path,enabled) VALUES(?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,root_path=excluded.root_path,enabled=1""",
                       (item["id"], item["name"], item["root_path"]))


def quick_fingerprint(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as stream:
        digest.update(stream.read(FINGERPRINT_CHUNK))
        if size > FINGERPRINT_CHUNK:
            stream.seek(max(0, size - FINGERPRINT_CHUNK))
            digest.update(stream.read(FINGERPRINT_CHUNK))
    return digest.hexdigest()


def probe(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60, check=True)
        data = json.loads(result.stdout)
        video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
        return {"duration": float(data.get("format", {}).get("duration") or video.get("duration") or 0),
                "width": video.get("width"), "height": video.get("height"),
                "video_codec": video.get("codec_name"), "audio_codec": audio.get("codec_name")}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return {"duration": None, "width": None, "height": None, "video_codec": None, "audio_codec": None}


def make_thumbnail(path: Path, media_id: str, duration: float | None) -> tuple[str, str | None]:
    THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)
    target = THUMBNAIL_ROOT / f"{media_id}.jpg"
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", str(min(max((duration or 10) * .1, 1), 30)),
                        "-i", str(path), "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(target)],
                       capture_output=True, timeout=90, check=True)
        return "ready", target.name
    except (FileNotFoundError, subprocess.SubprocessError):
        return "failed", None


def safe_media_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PermissionError("媒体路径超出媒体库") from exc
    return path


def _set_job(job_id: str, **values) -> None:
    with connect() as db:
        db.execute(f"UPDATE scan_jobs SET {','.join(f'{k}=?' for k in values)} WHERE id=?",
                   (*values.values(), job_id))


def run_scan(job_id: str) -> None:
    if not _scan_lock.acquire(blocking=False):
        _set_job(job_id, status="failed", message="已有扫描任务正在运行", finished_at=utcnow())
        return
    try:
        sync_libraries()
        _set_job(job_id, status="scanning", started_at=utcnow())
        with connect() as db:
            libraries = db.execute("SELECT * FROM libraries WHERE enabled=1").fetchall()
        discovered = []
        for library in libraries:
            root = Path(library["root_path"]).resolve()
            if root.exists():
                for path in root.rglob("*"):
                    if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
                        discovered.append((library, path, path.relative_to(root).as_posix(), path.stat()))
        discovered_keys = {(item[0]["id"], item[2]) for item in discovered}
        _set_job(job_id, total=len(discovered))
        with connect() as db:
            db.execute("UPDATE media SET available=0 WHERE kind='local'")
        errors = 0
        for index, (library, path, relative, stat) in enumerate(discovered, 1):
            try:
                with connect() as db:
                    row = db.execute("SELECT * FROM media WHERE kind='local' AND library_id=? AND location=?",
                                     (library["id"], relative)).fetchone()
                unchanged = bool(row and row["file_size"] == stat.st_size and row["file_mtime"] == stat.st_mtime)
                fingerprint = row["fingerprint"] if unchanged else quick_fingerprint(path)
                if row is None:
                    with connect() as db:
                        candidates = db.execute("""SELECT * FROM media WHERE kind='local' AND fingerprint=? AND available=0
                            ORDER BY last_scanned_at DESC""", (fingerprint,)).fetchall()
                        row = next((candidate for candidate in candidates
                                    if (candidate["library_id"], candidate["location"]) not in discovered_keys), None)
                media_id = row["id"] if row else str(uuid.uuid4())
                title = row["name"] if row and row["custom_title"] else path.name
                metadata = ({k: row[k] for k in ("duration", "width", "height", "video_codec", "audio_codec")}
                            if unchanged else probe(path))
                if unchanged and row["thumbnail_path"]:
                    thumb_status, thumb_path = row["thumbnail_status"], row["thumbnail_path"]
                else:
                    thumb_status, thumb_path = make_thumbnail(path, media_id, metadata["duration"])
                with connect() as db:
                    db.execute("""INSERT INTO media(id,name,kind,location,available,library_id,original_name,file_size,file_mtime,
                        fingerprint,duration,width,height,video_codec,audio_codec,imported_at,last_scanned_at,thumbnail_status,thumbnail_path)
                        VALUES(?,?,'local',?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET location=excluded.location,available=1,library_id=excluded.library_id,
                        original_name=excluded.original_name,file_size=excluded.file_size,file_mtime=excluded.file_mtime,
                        fingerprint=excluded.fingerprint,duration=excluded.duration,width=excluded.width,height=excluded.height,
                        video_codec=excluded.video_codec,audio_codec=excluded.audio_codec,last_scanned_at=excluded.last_scanned_at,
                        thumbnail_status=excluded.thumbnail_status,thumbnail_path=excluded.thumbnail_path,
                        name=CASE WHEN media.custom_title=1 THEN media.name ELSE excluded.name END""",
                               (media_id, title, relative, library["id"], path.name, stat.st_size, stat.st_mtime,
                                fingerprint, metadata["duration"], metadata["width"], metadata["height"],
                                metadata["video_codec"], metadata["audio_codec"], row["imported_at"] if row else utcnow(),
                                utcnow(), thumb_status, thumb_path))
            except Exception as exc:
                errors += 1
                _set_job(job_id, message=f"{relative}: {exc}")
            _set_job(job_id, status="probing" if index < len(discovered) else "thumbnailing",
                     processed=index, errors=errors)
        _set_job(job_id, status="completed", processed=len(discovered), errors=errors,
                 message=f"扫描完成，发现 {len(discovered)} 个视频，{errors} 个失败", finished_at=utcnow())
    except Exception as exc:
        _set_job(job_id, status="failed", message=str(exc), finished_at=utcnow())
    finally:
        _scan_lock.release()


def start_scan() -> str:
    job_id = str(uuid.uuid4())
    with connect() as db:
        db.execute("INSERT INTO scan_jobs(id,status) VALUES(?,'pending')", (job_id,))
    threading.Thread(target=run_scan, args=(job_id,), daemon=True).start()
    return job_id
