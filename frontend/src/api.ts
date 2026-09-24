import type { Collection, DownloadStatus, DownloadTask, FileActions, FileDeleteResult, Layout, MediaImportResult, MediaItem, MediaKind, MediaPage, ScanJob, Tag } from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `请求失败 (${response.status})`)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export const api = {
  media: () => request<MediaItem[]>('/api/media'),
  scan: () => request<{ job_id: string }>('/api/media/scan', { method: 'POST' }),
  scanStatus: (id: string) => request<ScanJob>(`/api/media/scan/${id}`),
  libraryMedia: (params: URLSearchParams) => request<MediaPage>(`/api/library/media?${params}`),
  updateMedia: (id: string, value: Partial<Pick<MediaItem, 'name' | 'notes' | 'rating' | 'favorite' | 'completed' | 'playback_position'>>) =>
    request<MediaItem>(`/api/library/media/${id}`, { method: 'PATCH', body: JSON.stringify(value) }),
  fileActions: (id: string) => request<FileActions>(`/api/library/media/${id}/file-actions`),
  renameMediaFile: (id: string, new_name: string) => request<MediaItem>(`/api/library/media/${id}/file-name`, { method: 'PUT', body: JSON.stringify({ new_name }) }),
  deleteMediaFile: (id: string) => request<FileDeleteResult>(`/api/library/media/${id}/file`, { method: 'DELETE' }),
  saveProgress: (id: string, position: number, duration?: number, completed?: boolean) =>
    request<{ ok: boolean }>(`/api/library/media/${id}/progress`, { method: 'PUT', body: JSON.stringify({ position, duration, completed }) }),
  tags: () => request<Tag[]>('/api/tags'),
  createTag: (name: string) => request<Tag>('/api/tags', { method: 'POST', body: JSON.stringify({ name }) }),
  renameTag: (id: string, name: string) => request<Tag>(`/api/tags/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteTag: (id: string) => request<void>(`/api/tags/${id}`, { method: 'DELETE' }),
  batchTags: (media_ids: string[], tag_ids: string[], action: 'add' | 'remove') =>
    request<{ updated: number }>('/api/tags/batch', { method: 'POST', body: JSON.stringify({ media_ids, tag_ids, action }) }),
  collections: () => request<Collection[]>('/api/collections'),
  createCollection: (name: string) => request<Collection>('/api/collections', { method: 'POST', body: JSON.stringify({ name }) }),
  renameCollection: (id: string, name: string) => request<Collection>(`/api/collections/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteCollection: (id: string) => request<void>(`/api/collections/${id}`, { method: 'DELETE' }),
  setCollectionItems: (id: string, media_ids: string[]) => request<{ updated: number }>(`/api/collections/${id}/items`, { method: 'PUT', body: JSON.stringify({ media_ids }) }),
  watchlist: () => request<MediaItem[]>('/api/watchlist'),
  addToWatchlist: (id: string) => request<MediaItem>(`/api/watchlist/${id}`, { method: 'POST' }),
  removeFromWatchlist: (id: string) => request<void>(`/api/watchlist/${id}`, { method: 'DELETE' }),
  reorderWatchlist: (media_ids: string[]) => request<MediaItem[]>('/api/watchlist/order', { method: 'PUT', body: JSON.stringify({ media_ids }) }),
  layout: () => request<Layout>('/api/layout'),
  saveLayout: (layout: Layout) => request<Layout>('/api/layout', { method: 'PUT', body: JSON.stringify(layout) }),
  createSource: (source: { name: string; kind: Exclude<MediaKind, 'local'>; location: string }) =>
    request<MediaItem>('/api/sources', { method: 'POST', body: JSON.stringify(source) }),
  updateSource: (id: string, source: { name: string; kind: Exclude<MediaKind, 'local'>; location: string }) =>
    request<MediaItem>(`/api/sources/${id}`, { method: 'PUT', body: JSON.stringify(source) }),
  deleteSource: (id: string) => request<void>(`/api/sources/${id}`, { method: 'DELETE' }),
  downloadStatus: () => request<DownloadStatus>('/api/downloads/status'),
  downloads: () => request<DownloadTask[]>('/api/downloads'),
  addDownload: (magnet: string) => request<{ hash: string }>('/api/downloads', { method: 'POST', body: JSON.stringify({ magnet }) }),
  pauseDownload: (hash: string) => request<void>(`/api/downloads/${hash}/pause`, { method: 'POST' }),
  resumeDownload: (hash: string) => request<void>(`/api/downloads/${hash}/resume`, { method: 'POST' }),
  deleteDownload: (hash: string, delete_files = false) => request<void>(`/api/downloads/${hash}`, { method: 'DELETE', body: JSON.stringify({ delete_files }) }),
  importMedia: (file: File, onProgress: (percent: number) => void) => new Promise<MediaImportResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/media/import')
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100))
    }
    xhr.onerror = () => reject(new Error('网络错误，视频上传失败'))
    xhr.onload = () => {
      const body = (() => { try { return JSON.parse(xhr.responseText) } catch { return null } })()
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as MediaImportResult)
      else reject(new Error(body?.detail || `视频上传失败 (${xhr.status})`))
    }
    const form = new FormData()
    form.append('file', file, file.name)
    xhr.send(form)
  }),
}
