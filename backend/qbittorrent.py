import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class QBitError(RuntimeError):
    pass


def normalize_hash(value: str) -> str:
    value = value.strip()
    if HASH_RE.fullmatch(value):
        return value.lower()
    if len(value) == 32:
        try:
            decoded = base64.b32decode(value.upper()).hex()
            if HASH_RE.fullmatch(decoded):
                return decoded
        except Exception:
            pass
    raise ValueError("无效的 BTIH 哈希")


def magnet_hash(uri: str) -> str:
    if len(uri) > 8192 or urlparse(uri).scheme.lower() != "magnet":
        raise ValueError("请输入有效的磁力链接")
    for xt in parse_qs(urlparse(uri).query).get("xt", []):
        prefix = "urn:btih:"
        if xt.lower().startswith(prefix):
            return normalize_hash(xt[len(prefix):])
    raise ValueError("磁力链接缺少 BTIH 标识")


def public_state(state: str, progress: float) -> str:
    if progress >= 1 or state in {"uploading", "stalledUP", "queuedUP", "forcedUP", "pausedUP", "stoppedUP"}:
        return "completed"
    if state in {"pausedDL", "stoppedDL"}:
        return "paused"
    if state in {"error", "missingFiles", "unknown"}:
        return "error"
    if state in {"metaDL", "checkingDL", "checkingUP", "checkingResumeData", "moving"}:
        return "checking"
    if state in {"queuedDL", "queuedUP"}:
        return "queued"
    return "downloading"


class QBitClient:
    def __init__(self):
        self.base_url = os.getenv("QBT_URL", "http://qbittorrent:8080").rstrip("/")
        self.timeout = float(os.getenv("QBT_TIMEOUT", "8"))
        self.client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        self._authenticated = False

    def close(self):
        self.client.close()

    def _api_key(self) -> str:
        path = os.getenv("QBT_API_KEY_FILE", "")
        if path and Path(path).is_file():
            return Path(path).read_text(encoding="utf-8").strip()
        return os.getenv("QBT_API_KEY", "").strip()

    def _authenticate(self):
        key = self._api_key()
        if key:
            self.client.headers["Authorization"] = f"Bearer {key}"
            self._authenticated = True
            return
        username, password = os.getenv("QBT_USERNAME", ""), os.getenv("QBT_PASSWORD", "")
        if not username or not password:
            raise QBitError("qBittorrent 尚未配置认证信息")
        try:
            response = self.client.post("/api/v2/auth/login", data={"username": username, "password": password})
        except httpx.HTTPError as exc:
            raise QBitError("无法连接 qBittorrent") from exc
        if response.status_code not in (200, 204) or (response.status_code == 200 and response.text.strip() not in ("", "Ok.")):
            raise QBitError("qBittorrent 认证失败")
        self._authenticated = True

    def request(self, method: str, path: str, **kwargs):
        if not self._authenticated:
            self._authenticate()
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise QBitError("无法连接 qBittorrent") from exc
        if response.status_code in (401, 403):
            self._authenticated = False
            raise QBitError("qBittorrent 认证失败")
        if response.status_code >= 400:
            raise QBitError(f"qBittorrent 请求失败 ({response.status_code})")
        return response

    def status(self):
        version = self.request("GET", "/api/v2/app/version").text
        transfer = self.request("GET", "/api/v2/transfer/info").json()
        return {"connected": True, "version": version, "download_speed": transfer.get("dl_info_speed", 0),
                "upload_speed": transfer.get("up_info_speed", 0), "error": None}

    def torrents(self):
        rows = self.request("GET", "/api/v2/torrents/info", params={"category": "watch2"}).json()
        return [{**row, "hash": row["hash"].lower(), "status": public_state(row.get("state", "unknown"), row.get("progress", 0))}
                for row in rows]

    def add(self, magnet: str):
        info_hash = magnet_hash(magnet)
        if any(item["hash"] == info_hash for item in self.torrents()):
            raise FileExistsError("该任务已经存在")
        categories = self.request("GET", "/api/v2/torrents/categories").json()
        if "watch2" not in categories:
            self.request("POST", "/api/v2/torrents/createCategory",
                         data={"category": "watch2", "savePath": "/downloads/complete"})
        preferences = {"save_path": "/downloads/complete", "temp_path_enabled": True,
                       "temp_path": "/downloads/incomplete"}
        self.request("POST", "/api/v2/app/setPreferences", data={"json": json.dumps(preferences)})
        response = self.request("POST", "/api/v2/torrents/add", data={"urls": magnet, "category": "watch2",
                                "savepath": "/downloads/complete", "stopped": "false"})
        if response.text.strip() != "Ok.":
            raise QBitError("qBittorrent 未接受下载任务")
        return info_hash

    def action(self, info_hash: str, action: str, delete_files: bool = False):
        info_hash = normalize_hash(info_hash)
        endpoints = {"pause": "stop", "resume": "start", "delete": "delete"}
        endpoint = endpoints[action]
        data = {"hashes": info_hash}
        if action == "delete":
            data["deleteFiles"] = json.dumps(bool(delete_files))
        self.request("POST", f"/api/v2/torrents/{endpoint}", data=data)

    def files(self, info_hash: str):
        return self.request("GET", "/api/v2/torrents/files", params={"hash": normalize_hash(info_hash)}).json()
