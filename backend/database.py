import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/app.db"))


@contextmanager
def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _columns(db, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _add_column(db, table: str, definition: str) -> None:
    if definition.split()[0] not in _columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _migrate_legacy_media(db) -> None:
    additions = [
        "library_id TEXT", "original_name TEXT", "file_size INTEGER", "file_mtime REAL",
        "fingerprint TEXT", "full_hash TEXT", "duration REAL", "width INTEGER", "height INTEGER",
        "video_codec TEXT", "audio_codec TEXT", "imported_at TEXT", "last_scanned_at TEXT",
        "favorite INTEGER NOT NULL DEFAULT 0", "rating INTEGER", "notes TEXT NOT NULL DEFAULT ''",
        "watch_count INTEGER NOT NULL DEFAULT 0", "last_watched_at TEXT", "playback_position REAL NOT NULL DEFAULT 0",
        "completed INTEGER NOT NULL DEFAULT 0", "thumbnail_status TEXT NOT NULL DEFAULT 'pending'",
        "thumbnail_path TEXT", "custom_title INTEGER NOT NULL DEFAULT 0",
    ]
    for definition in additions:
        _add_column(db, "media", definition)
    db.execute("UPDATE media SET original_name=name WHERE original_name IS NULL")
    db.execute("UPDATE media SET imported_at=datetime('now') WHERE imported_at IS NULL")
    db.execute("UPDATE media SET last_scanned_at=datetime('now') WHERE last_scanned_at IS NULL")
    db.execute("UPDATE media SET library_id='default' WHERE kind='local' AND library_id IS NULL")
    layout_row = db.execute("SELECT value FROM settings WHERE key='layout'").fetchone()
    layout = json.loads(layout_row[0]) if layout_row else None
    changed = False
    for row in db.execute("SELECT id FROM media").fetchall():
        old_id = row[0]
        try:
            uuid.UUID(old_id)
            continue
        except (ValueError, AttributeError):
            new_id = str(uuid.uuid4())
        db.execute("UPDATE media SET id=? WHERE id=?", (new_id, old_id))
        if layout:
            for slot in layout["slots"]:
                if slot.get("media_id") == old_id:
                    slot["media_id"] = new_id
                    changed = True
    if changed:
        db.execute("UPDATE settings SET value=? WHERE key='layout'", (json.dumps(layout),))


def _remove_legacy_location_constraint(db) -> None:
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='media'").fetchone()[0]
    if "UNIQUE(kind, location)" not in sql and "UNIQUE(kind,location)" not in sql:
        return
    columns = [row[1] for row in db.execute("PRAGMA table_info(media)")]
    db.commit()
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("ALTER TABLE media RENAME TO media_legacy")
    db.execute("""CREATE TABLE media (
        id TEXT PRIMARY KEY, name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('local','direct','hls')),
        location TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 1)""")
    shared = [name for name in columns if name in _columns(db, "media")]
    db.execute(f"INSERT INTO media({','.join(shared)}) SELECT {','.join(shared)} FROM media_legacy")
    db.execute("DROP TABLE media_legacy")
    db.commit()
    db.execute("PRAGMA foreign_keys=ON")


def init_database() -> None:
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS libraries (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, root_path TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS media (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('local', 'direct', 'hls')),
                location TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 1);
        """)
        _remove_legacy_location_constraint(db)
        _migrate_legacy_media(db)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tags (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS media_tags (
                media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY(media_id, tag_id));
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS collection_items (
                collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                position INTEGER NOT NULL, PRIMARY KEY(collection_id, media_id));
            CREATE TABLE IF NOT EXISTS watchlist_items (
                media_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
                position INTEGER NOT NULL UNIQUE,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS scan_jobs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT, finished_at TEXT);
            CREATE TABLE IF NOT EXISTS download_imports (
                torrent_hash TEXT NOT NULL, relative_path TEXT NOT NULL,
                media_id TEXT REFERENCES media(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '',
                imported_at TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(torrent_hash, relative_path));
        """)
        if db.execute("SELECT 1 FROM settings WHERE key='layout'").fetchone() is None:
            positions = ["main"] + [f"p{i}" for i in range(12)]
            slots = [{"slot_id": i, "position": p, "media_id": None,
                      "muted": p != "main", "volume": 1.0, "playing": False} for i, p in enumerate(positions)]
            db.execute("INSERT INTO settings(key,value) VALUES('layout',?)", (json.dumps({"slots": slots}),))
        db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_media_location ON media(library_id, location);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_local_library_location ON media(library_id,location) WHERE kind='local';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_remote_location ON media(kind,location) WHERE kind!='local';
            CREATE INDEX IF NOT EXISTS idx_media_fingerprint ON media(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_media_available ON media(available);
            CREATE INDEX IF NOT EXISTS idx_media_imported ON media(imported_at);
            CREATE INDEX IF NOT EXISTS idx_download_import_media ON download_imports(media_id);
        """)
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('schema_version','4')")
