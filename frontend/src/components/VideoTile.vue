<script setup lang="ts">
import Hls from 'hls.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { MediaItem, Slot } from '../types'

const props = defineProps<{ slot: Slot; media?: MediaItem; selected: boolean }>()
const emit = defineEmits<{ select: []; focus: []; fullscreen: []; state: [playing: boolean]; progress: [position: number, duration: number] }>()
const video = ref<HTMLVideoElement>()
const error = ref('')
let hls: Hls | null = null
let lastProgress = 0

const isMain = computed(() => props.slot.position === 'main')

function destroyHls() {
  hls?.destroy()
  hls = null
}

async function load() {
  destroyHls()
  error.value = ''
  const element = video.value
  if (!element) return
  element.removeAttribute('src')
  element.load()
  if (!props.media) return
  if (!props.media.available) {
    error.value = '文件不可用，请重新扫描媒体库'
    return
  }
  const url = props.media.playback_url
  if (props.media.kind === 'hls' && Hls.isSupported()) {
    hls = new Hls({ enableWorker: true })
    hls.loadSource(url)
    hls.attachMedia(element)
    hls.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) error.value = hlsError(data.type)
    })
  } else if (props.media.kind === 'hls' && !element.canPlayType('application/vnd.apple.mpegurl')) {
    error.value = '此浏览器不支持 HLS 播放'
    return
  } else {
    element.src = url
  }
  await nextTick()
  if (props.slot.playing) void play()
}

function hlsError(type: string) {
  if (type === Hls.ErrorTypes.NETWORK_ERROR) return '视频网络请求失败，可能受到 CORS 或防盗链限制'
  if (type === Hls.ErrorTypes.MEDIA_ERROR) return '浏览器无法解码该视频'
  return 'HLS 播放失败'
}

async function play() {
  if (!video.value || !props.media) return
  try {
    await video.value.play()
    error.value = ''
  } catch {
    error.value = '浏览器阻止了播放，请点击开始播放或重试'
  }
}

function pause() { video.value?.pause() }
function retry() { void load() }
function restoreProgress() {
  if (video.value && props.media?.playback_position && video.value.duration > props.media.playback_position + 15) {
    video.value.currentTime = props.media.playback_position
  }
}
function reportProgress(force = false) {
  const element = video.value
  if (!element || !props.media || !Number.isFinite(element.duration)) return
  if (force || element.currentTime - lastProgress >= 10) {
    lastProgress = element.currentTime
    emit('progress', element.currentTime, element.duration)
  }
}

watch(() => props.media?.id, load)
watch(() => props.slot.muted, value => { if (video.value) video.value.muted = value })
watch(() => props.slot.volume, value => { if (video.value) video.value.volume = value })

onMounted(() => {
  if (video.value) {
    video.value.muted = props.slot.muted
    video.value.volume = props.slot.volume
  }
  void load()
})
onBeforeUnmount(() => { reportProgress(true); destroyHls() })
defineExpose({ play, pause, retry })
</script>

<template>
  <article
    class="video-tile"
    :class="{ main: isMain, selected, empty: !media }"
    :data-position="slot.position"
    @click="emit('select')"
    @dblclick="isMain ? emit('fullscreen') : emit('focus')"
  >
    <video
      ref="video"
      playsinline
      :controls="isMain"
      :muted="slot.muted"
      @play="emit('state', true)"
      @pause="emit('state', false); reportProgress(true)"
      @loadedmetadata="restoreProgress"
      @timeupdate="reportProgress()"
      @ended="reportProgress(true)"
      @error="error = '视频加载失败，格式可能不受支持或网络源受限'"
    />
    <div v-if="!media" class="empty-state"><span>+</span><small>选择视频</small></div>
    <div v-else-if="error" class="error-state">
      <strong>{{ media.name }}</strong><span>{{ error }}</span><button @click.stop="retry">重试</button>
    </div>
    <div class="tile-label">
      <span>{{ isMain ? '主画面' : `#${slot.slot_id + 1}` }}</span>
      <strong>{{ media?.name || '空播放位' }}</strong>
      <i v-if="slot.muted">静音</i>
    </div>
  </article>
</template>
