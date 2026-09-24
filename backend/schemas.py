from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator

MediaKind = Literal["local", "direct", "hls"]


class Tag(BaseModel):
    id: str
    name: str


class MediaItem(BaseModel):
    id: str
    name: str
    kind: MediaKind
    location: str
    available: bool
    playback_url: str
    library_id: str | None = None
    original_name: str | None = None
    file_size: int | None = None
    file_mtime: float | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    imported_at: str | None = None
    last_scanned_at: str | None = None
    favorite: bool = False
    rating: int | None = None
    notes: str = ""
    watch_count: int = 0
    last_watched_at: str | None = None
    playback_position: float = 0
    completed: bool = False
    thumbnail_status: str = "pending"
    thumbnail_url: str | None = None
    tags: list[Tag] = Field(default_factory=list)


class MediaPage(BaseModel):
    items: list[MediaItem]
    page: int
    page_size: int
    total: int
    pages: int


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["direct", "hls"]
    location: HttpUrl

    @model_validator(mode="after")
    def validate_hls_url(self):
        if self.kind == "hls" and ".m3u8" not in str(self.location).lower():
            raise ValueError("HLS 地址必须包含 .m3u8")
        return self


class MediaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    favorite: bool | None = None
    completed: bool | None = None
    playback_position: float | None = Field(default=None, ge=0)


class ProgressUpdate(BaseModel):
    position: float = Field(ge=0)
    duration: float | None = Field(default=None, ge=0)
    completed: bool | None = None


class NameCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagBatch(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=500)
    tag_ids: list[str] = Field(max_length=100)
    action: Literal["add", "remove"]


class CollectionItems(BaseModel):
    media_ids: list[str] = Field(max_length=1000)


class WatchlistOrder(BaseModel):
    media_ids: list[str] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(self.media_ids) != len(set(self.media_ids)):
            raise ValueError("播放列表不能包含重复视频")
        return self


class MagnetCreate(BaseModel):
    magnet: str = Field(min_length=20, max_length=8192)


class DownloadDelete(BaseModel):
    delete_files: bool = False


class Slot(BaseModel):
    slot_id: int = Field(ge=0, le=12)
    position: str
    media_id: str | None = None
    muted: bool = True
    volume: float = Field(ge=0, le=1)
    playing: bool = False


class Layout(BaseModel):
    slots: list[Slot]

    @model_validator(mode="after")
    def validate_layout(self):
        if len(self.slots) != 13 or {s.slot_id for s in self.slots} != set(range(13)):
            raise ValueError("布局必须包含 13 个唯一槽位")
        if {s.position for s in self.slots} != {"main", *(f"p{i}" for i in range(12))}:
            raise ValueError("布局位置必须包含 main 和 p0-p11")
        if sum(not s.muted for s in self.slots) > 1:
            raise ValueError("最多只能有一个未静音的播放器")
        return self
