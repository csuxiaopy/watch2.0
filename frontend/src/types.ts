export type MediaKind = 'local' | 'direct' | 'hls'

export interface MediaItem {
  id: string
  name: string
  kind: MediaKind
  location: string
  available: boolean
  playback_url: string
  library_id?: string | null
  original_name?: string | null
  file_size?: number | null
  file_mtime?: number | null
  duration?: number | null
  width?: number | null
  height?: number | null
  video_codec?: string | null
  audio_codec?: string | null
  imported_at?: string | null
  favorite: boolean
  rating?: number | null
  notes: string
  watch_count: number
  playback_position: number
  completed: boolean
  thumbnail_status: string
  thumbnail_url?: string | null
  tags: Tag[]
}

export interface Tag { id: string; name: string; count?: number }
export interface Collection { id: string; name: string; count: number }
export interface MediaPage { items: MediaItem[]; page: number; page_size: number; total: number; pages: number }
export interface ScanJob { id: string; status: string; total: number; processed: number; errors: number; message: string }

export interface Slot {
  slot_id: number
  position: string
  media_id: string | null
  muted: boolean
  volume: number
  playing: boolean
}

export interface Layout { slots: Slot[] }

export interface DownloadStatus { connected: boolean; version?: string | null; download_speed: number; upload_speed: number; error?: string | null }
export interface DownloadTask {
  hash: string; name: string; status: 'queued'|'downloading'|'paused'|'checking'|'completed'|'error'
  progress: number; size: number; dlspeed: number; upspeed: number; eta: number; state: string
  imported_media: { media_id: string; name: string }[]
}
export interface MediaImportResult { original_name: string; saved_name: string; relative_path: string; size: number }
export interface FileActions {
  local: boolean; can_rename: boolean; delete_mode: 'single_file' | 'torrent' | 'record_only' | null
  affected_media: number; reason?: string | null
}
export interface FileDeleteResult { deleted_media_ids: string[]; deleted_files: string[]; torrent_hash?: string | null }
