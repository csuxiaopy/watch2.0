<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MediaItem } from '../types'

const props = defineProps<{ media: MediaItem[]; selectedId: string | null }>()
const emit = defineEmits<{
  assign: [item: MediaItem]
  remove: [item: MediaItem]
  move: [index: number, direction: -1 | 1]
}>()

const query = ref('')
const filtered = computed(() => props.media.filter(item => item.name.toLowerCase().includes(query.value.toLowerCase())))
function move(item: MediaItem, direction: -1 | 1) {
  const index = props.media.indexOf(item)
  if (index + direction < 0 || index + direction >= props.media.length) return
  emit('move', index, direction)
}
</script>

<template>
  <aside class="library">
    <div class="library-head">
      <div><small>WATCHLIST</small><h2>想看列表</h2></div>
    </div>
    <div class="library-actions">
      <input v-model="query" placeholder="搜索视频…" />
    </div>
    <p class="assign-hint">点击视频，将它放入当前选中的播放位</p>
    <div class="media-list">
      <button
        v-for="item in filtered"
        :key="item.id"
        class="media-row"
        :class="{ active: selectedId === item.id, unavailable: !item.available }"
        @click="emit('assign', item)"
      >
        <span class="kind">{{ item.kind === 'local' ? '本地' : item.kind === 'hls' ? 'HLS' : '直链' }}</span>
        <span class="media-name"><strong>{{ item.name }}</strong><small>{{ item.available ? item.location : '文件不可用' }}</small></span>
        <span class="row-tools" @click.stop>
          <i :class="{ disabled: props.media.indexOf(item) === 0 }" @click="move(item, -1)">↑</i>
          <i :class="{ disabled: props.media.indexOf(item) === props.media.length - 1 }" @click="move(item, 1)">↓</i>
          <i class="danger" @click="emit('remove', item)">移出</i>
        </span>
      </button>
      <div v-if="!filtered.length" class="no-media">想看列表为空<br><small>请前往“管理媒体库”添加想看的视频</small></div>
    </div>
  </aside>
</template>
