<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import type { DownloadStatus, DownloadTask } from '../types'

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const emit = defineEmits<{ close: []; mediaChanged: []; watchlistChanged: [] }>()
const status = ref<DownloadStatus>({ connected: false, download_speed: 0, upload_speed: 0 })
const tasks = ref<DownloadTask[]>([])
const magnet = ref('')
const loading = ref(false)
const error = ref('')
let timer: number | undefined
const formatBytes = (n: number) => n ? `${(n / 1024 / 1024).toFixed(n > 1024 ** 3 ? 1 : 0)} MB` : '0 MB'
const formatSpeed = (n: number) => `${formatBytes(n)}/s`

async function refresh() {
  if (document.visibilityState === 'hidden') return
  status.value = await api.downloadStatus()
  if (status.value.connected) tasks.value = await api.downloads()
}
async function act(run: () => Promise<unknown>) {
  try { error.value = ''; await run(); await refresh() } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
}
async function add() {
  if (!magnet.value.trim()) return
  loading.value = true
  await act(async () => { await api.addDownload(magnet.value.trim()); magnet.value = '' })
  loading.value = false
}
async function remove(task: DownloadTask, files: boolean) {
  if (files) {
    if (!window.confirm(`确定删除“${task.name}”任务及已下载文件吗？`)) return
    if (!window.confirm('此操作会永久删除下载目录中的文件，无法从 Watch 恢复。再次确认？')) return
  } else if (!window.confirm(`移除“${task.name}”任务但保留文件？`)) return
  await act(() => api.deleteDownload(task.hash, files))
  emit('mediaChanged')
}
async function addWanted(mediaId: string) { await act(() => api.addToWatchlist(mediaId)); emit('watchlistChanged') }
onMounted(() => { void refresh().catch(e => error.value = String(e)); timer = window.setInterval(() => void refresh().catch(() => undefined), 3000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section :class="embedded ? 'download-panel' : 'manager download-manager'">
    <header v-if="!embedded" class="manager-head"><div><small>QBITTORRENT-NOX</small><h1>磁力下载</h1></div><div class="manager-actions"><button @click="refresh">刷新</button><button @click="emit('close')">返回媒体库</button></div></header>
    <header v-else class="download-panel-head"><div><small>QBITTORRENT-NOX</small><h2>磁力下载</h2></div><button @click="refresh">刷新</button></header>
    <div class="download-summary" :class="{ offline: !status.connected }">
      <strong>{{ status.connected ? `已连接 · qBittorrent ${status.version || ''}` : '下载器未连接' }}</strong>
      <span v-if="status.connected">↓ {{ formatSpeed(status.download_speed) }}　↑ {{ formatSpeed(status.upload_speed) }}</span>
      <span v-else>{{ status.error }}</span>
    </div>
    <form class="magnet-form" @submit.prevent="add"><input v-model="magnet" aria-label="磁力链接" placeholder="粘贴 magnet:?xt=urn:btih:…" /><button class="primary" :disabled="loading || !status.connected">{{ loading ? '正在提交…' : '添加下载' }}</button></form>
    <p v-if="error" class="download-error">{{ error }}</p>
    <div v-if="!tasks.length" class="manager-empty"><strong>暂无下载任务</strong><small>添加磁力链接后，完成的视频会自动进入“下载的视频”媒体库。</small></div>
    <div v-else class="download-list">
      <article v-for="task in tasks" :key="task.hash">
        <div class="download-title"><strong>{{ task.name || task.hash }}</strong><span>{{ task.status }}</span></div>
        <div class="progress-track"><i :style="{ width: `${Math.round(task.progress * 100)}%` }"></i></div>
        <div class="download-meta"><span>{{ Math.round(task.progress * 100) }}% · {{ formatBytes(task.size) }}</span><span>↓ {{ formatSpeed(task.dlspeed) }}　↑ {{ formatSpeed(task.upspeed) }}</span></div>
        <div class="download-actions">
          <button v-if="task.status === 'paused'" @click="act(() => api.resumeDownload(task.hash))">继续</button><button v-else-if="task.status !== 'completed'" @click="act(() => api.pauseDownload(task.hash))">暂停</button>
          <button v-for="item in task.imported_media" :key="item.media_id" @click="addWanted(item.media_id)">加入想看：{{ item.name }}</button>
          <button @click="remove(task, false)">移除任务</button><button class="danger-button" @click="remove(task, true)">删除任务和文件</button>
        </div>
      </article>
    </div>
  </section>
</template>
