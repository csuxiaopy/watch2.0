<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'

type QueueItem = {
  id: string; file: File; progress: number
  status: 'pending' | 'uploading' | 'success' | 'failed'; savedName?: string; error?: string
}

const emit = defineEmits<{ changed: []; watchlistChanged: [] }>()
const input = ref<HTMLInputElement>()
const queue = ref<QueueItem[]>([])
const running = ref(false)
const scanMessage = ref('')
const overall = computed(() => queue.value.length ? Math.round(queue.value.reduce((sum, item) => sum + item.progress, 0) / queue.value.length) : 0)

function choose() { input.value?.click() }
function selected(event: Event) {
  const files = [...((event.target as HTMLInputElement).files || [])]
  queue.value = files.map((file, index) => ({ id: `${file.name}-${file.size}-${index}`, file, progress: 0, status: 'pending' }))
  ;(event.target as HTMLInputElement).value = ''
}
async function waitForScan(jobId: string) {
  while (true) {
    const job = await api.scanStatus(jobId)
    scanMessage.value = `${job.processed}/${job.total} · ${job.message || job.status}`
    if (['completed', 'failed'].includes(job.status)) {
      if (job.status === 'failed') throw new Error(job.message || '媒体扫描失败')
      return
    }
    await new Promise(resolve => window.setTimeout(resolve, 500))
  }
}
async function upload() {
  if (running.value || !queue.value.length) return
  running.value = true; scanMessage.value = ''
  let successes = 0
  for (const item of queue.value) {
    if (item.status === 'success') continue
    item.progress = 0; item.error = undefined
    item.status = 'uploading'
    try {
      const result = await api.importMedia(item.file, progress => { item.progress = progress })
      item.progress = 100; item.status = 'success'; item.savedName = result.saved_name; successes++
    } catch (error) {
      item.status = 'failed'; item.error = error instanceof Error ? error.message : String(error)
    }
  }
  if (successes) {
    try {
      scanMessage.value = '正在扫描新视频…'
      const { job_id } = await api.scan()
      await waitForScan(job_id)
      emit('changed'); emit('watchlistChanged')
    } catch (error) { scanMessage.value = error instanceof Error ? error.message : String(error) }
  }
  running.value = false
}
function fmtSize(size: number) { return `${(size / 1024 / 1024).toFixed(size >= 1024 ** 3 ? 0 : 1)} MB` }
</script>

<template>
  <section class="import-panel">
    <header class="import-panel-head"><div><small>LOCAL IMPORT</small><h2>视频移入</h2></div><button :disabled="running" @click="choose">选择视频</button></header>
    <input ref="input" class="file-input" type="file" multiple accept="video/*,.mkv,.avi,.flv,.ts,.m4v,.ogv" @change="selected">
    <div class="import-intro"><strong>将电脑中的视频复制到媒体目录</strong><p>可以一次选择多个文件；原文件不会移动或删除。同名文件会自动追加序号。</p><button class="primary" :disabled="running" @click="choose">＋ 打开文件选择器</button></div>
    <div v-if="queue.length" class="import-queue">
      <div class="import-overall"><span>{{ running ? '正在移入' : '待移入' }} {{ queue.length }} 个视频</span><strong>{{ overall }}%</strong></div>
      <article v-for="item in queue" :key="item.id" :class="item.status">
        <div><strong>{{ item.file.name }}</strong><small>{{ fmtSize(item.file.size) }}<template v-if="item.savedName && item.savedName !== item.file.name"> · 保存为 {{ item.savedName }}</template></small></div>
        <span>{{ item.status === 'pending' ? '等待' : item.status === 'uploading' ? `${item.progress}%` : item.status === 'success' ? '完成' : item.error }}</span>
        <div class="progress-track"><i :style="{ width: `${item.progress}%` }"></i></div>
      </article>
      <footer><span>{{ scanMessage }}</span><button class="primary" :disabled="running || queue.every(item => item.status === 'success')" @click="upload">{{ running ? '处理中…' : '开始移入' }}</button></footer>
    </div>
  </section>
</template>
