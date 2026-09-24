<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from './api'
import { toggleFullscreen } from './fullscreen'
import { focusSlot } from './layout'
import MediaLibrary from './components/MediaLibrary.vue'
import LibraryManager from './components/LibraryManager.vue'
import VideoTile from './components/VideoTile.vue'
import type { Layout, MediaItem, Slot } from './types'

type TileApi = { play: () => Promise<void>; pause: () => void; retry: () => void }
const media = ref<MediaItem[]>([])
const watchlist = ref<MediaItem[]>([])
const layout = ref<Layout>({ slots: [] })
const selectedSlotId = ref(0)
const libraryOpen = ref(true)
const started = ref(false)
const message = ref('')
const tileRefs = ref<TileApi[]>([])
const videoGrid = ref<HTMLElement>()
const isFullscreen = ref(false)
const managerOpen = ref(false)
let saveTimer: number | undefined

const mediaById = computed(() => new Map(media.value.map(item => [item.id, item])))
const selectedSlot = computed(() => layout.value.slots.find(slot => slot.slot_id === selectedSlotId.value))

async function load() {
  try {
    const [items, wanted, saved] = await Promise.all([api.media(), api.watchlist(), api.layout()])
    media.value = items
    watchlist.value = wanted
    layout.value = saved
    selectedSlotId.value = saved.slots.find(slot => slot.position === 'main')?.slot_id ?? 0
  } catch (error) { notify(error) }
}

function notify(value: unknown) {
  message.value = value instanceof Error ? value.message : String(value)
  window.setTimeout(() => { message.value = '' }, 3500)
}

function scheduleSave() {
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(async () => {
    try { layout.value = await api.saveLayout(layout.value) } catch (error) { notify(error) }
  }, 250)
}

function assign(item: MediaItem) {
  const slot = selectedSlot.value
  if (!slot) return
  slot.media_id = item.id
  slot.playing = started.value
  scheduleSave()
}

function focus(slot: Slot) {
  if (!focusSlot(layout.value, slot.slot_id)) return
  selectedSlotId.value = slot.slot_id
  scheduleSave()
}

async function playAll() {
  started.value = true
  layout.value.slots.forEach(slot => { slot.playing = true })
  await Promise.allSettled(tileRefs.value.map(tile => tile?.play()))
  scheduleSave()
}

function pauseAll() {
  layout.value.slots.forEach(slot => { slot.playing = false })
  tileRefs.value.forEach(tile => tile?.pause())
  scheduleSave()
}

function muteAll() {
  layout.value.slots.forEach(slot => { slot.muted = true })
  scheduleSave()
}

function onPlayback(slot: Slot, playing: boolean) {
  slot.playing = playing
  scheduleSave()
}

function syncFullscreenState() {
  isFullscreen.value = document.fullscreenElement === videoGrid.value
}

async function toggleWallFullscreen() {
  if (!videoGrid.value) return
  try {
    await toggleFullscreen(videoGrid.value)
  } catch (error) {
    notify(error instanceof Error ? error : '无法进入全屏模式')
  }
}

async function refreshMedia() { media.value = await api.media() }
async function refreshWatchlist() { watchlist.value = await api.watchlist() }
async function removeWanted(item: MediaItem) {
  try { await api.removeFromWatchlist(item.id); await refreshWatchlist(); notify('已从想看列表移出') }
  catch (error) { notify(error) }
}
async function moveWanted(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= watchlist.value.length) return
  const next = [...watchlist.value]; [next[index], next[target]] = [next[target], next[index]]
  try { watchlist.value = await api.reorderWatchlist(next.map(item => item.id)) }
  catch (error) { notify(error); await refreshWatchlist() }
}
function onProgress(slot: Slot, position: number, duration: number) {
  const item = slot.media_id ? mediaById.value.get(slot.media_id) : undefined
  if (item?.kind === 'local') void api.saveProgress(item.id, position, duration).catch(() => undefined)
}

onMounted(() => {
  document.addEventListener('fullscreenchange', syncFullscreenState)
  void load()
})
onBeforeUnmount(() => document.removeEventListener('fullscreenchange', syncFullscreenState))
</script>

<template>
  <main class="app-shell" :class="{ 'library-closed': !libraryOpen }">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">W</span><div><strong>WATCH 2.0</strong><small>PERSONAL VIDEO WALL</small></div></div>
      <div class="global-controls">
        <button class="primary" @click="playAll">▶ {{ started ? '全部播放' : '开始播放' }}</button>
        <button @click="pauseAll">Ⅱ 全部暂停</button>
        <button @click="muteAll">⌁ 全部静音</button>
        <button @click="toggleWallFullscreen">⛶ {{ isFullscreen ? '退出全屏' : '视频墙全屏' }}</button>
        <button @click="libraryOpen = !libraryOpen">{{ libraryOpen ? '隐藏列表' : '显示列表' }}</button>
        <button @click="managerOpen = true">管理媒体库</button>
      </div>
      <div class="status"><i></i>{{ media.length }} 个视频源</div>
    </header>

    <section class="workspace">
      <div v-if="layout.slots.length" ref="videoGrid" class="video-grid" :class="{ fullscreen: isFullscreen }">
        <button v-if="isFullscreen" class="exit-fullscreen" @click="toggleWallFullscreen">⛶ 退出全屏</button>
        <VideoTile
          v-for="slot in layout.slots"
          :key="slot.slot_id"
          ref="tileRefs"
          :slot="slot"
          :media="slot.media_id ? mediaById.get(slot.media_id) : undefined"
          :selected="selectedSlotId === slot.slot_id"
          @select="selectedSlotId = slot.slot_id"
          @focus="focus(slot)"
          @fullscreen="toggleWallFullscreen"
          @state="onPlayback(slot, $event)"
          @progress="(position, duration) => onProgress(slot, position, duration)"
        />
      </div>
      <div v-else class="loading">正在加载视频墙…</div>
      <MediaLibrary
        v-if="libraryOpen"
        :media="watchlist"
        :selected-id="selectedSlot?.media_id || null"
        @assign="assign"
        @remove="removeWanted"
        @move="moveWanted"
      />
    </section>
    <div v-if="!started && !managerOpen" class="start-overlay"><button @click="playAll"><span>▶</span><strong>开始播放</strong><small>点击后启动全部已配置的视频</small></button></div>
    <LibraryManager v-if="managerOpen" :watchlist-ids="watchlist.map(item => item.id)" @close="managerOpen=false" @changed="refreshMedia" @watchlist-changed="refreshWatchlist" />
    <div v-if="message" class="toast">{{ message }}</div>
  </main>
</template>
