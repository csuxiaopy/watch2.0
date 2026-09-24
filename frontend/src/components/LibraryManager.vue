<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import type { Collection, FileActions, MediaItem, MediaPage, ScanJob, Tag } from '../types'
import DownloadManager from './DownloadManager.vue'
import MediaImporter from './MediaImporter.vue'

const props = defineProps<{ watchlistIds: string[] }>()
const emit = defineEmits<{ close: []; changed: []; watchlistChanged: []; layoutChanged: [] }>()
const page = ref<MediaPage>({ items: [], page: 1, page_size: 48, total: 0, pages: 1 })
const tags = ref<Tag[]>([]), collections = ref<Collection[]>([])
const query = ref(''), tagId = ref(''), collectionId = ref(''), filter = ref('all'), sort = ref('imported_desc')
const view = ref<'grid' | 'table'>('grid'), loading = ref(false), error = ref(''), selected = ref<Set<string>>(new Set())
const detail = ref<MediaItem | null>(null), scanJob = ref<ScanJob | null>(null)
const sourceEditing = ref(false)
const fileActions = ref<FileActions | null>(null), fileName = ref(''), fileBusy = ref(false), fileError = ref('')
const section = ref<'media' | 'downloads' | 'import'>('media')
const sourceForm = reactive<{ id?: string; name: string; kind: 'direct' | 'hls'; location: string }>({ name: '', kind: 'direct', location: '' })
let queryTimer: number | undefined
const selectedCount = computed(() => selected.value.size)
const watchlistSet = computed(() => new Set(props.watchlistIds))

async function load(targetPage = 1) {
  loading.value = true; error.value = ''
  const params = new URLSearchParams({ page: String(targetPage), page_size: '48', sort: sort.value })
  if (query.value) params.set('query', query.value)
  if (tagId.value) params.set('tag_id', tagId.value)
  if (collectionId.value) params.set('collection_id', collectionId.value)
  if (filter.value === 'favorite') params.set('favorite', 'true')
  if (filter.value === 'completed') params.set('completed', 'true')
  if (filter.value === 'missing') params.set('available', 'false')
  try { page.value = await api.libraryMedia(params) } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { loading.value = false }
}
async function loadFacets() { [tags.value, collections.value] = await Promise.all([api.tags(), api.collections()]) }
function toggle(id: string) { const next = new Set(selected.value); next.has(id) ? next.delete(id) : next.add(id); selected.value = next }
async function saveDetail() {
  if (!detail.value) return
  detail.value = await api.updateMedia(detail.value.id, { name: detail.value.name, notes: detail.value.notes,
    rating: detail.value.rating, favorite: detail.value.favorite, completed: detail.value.completed })
  await load(page.value.page); emit('changed')
}
async function addTag(tag: Tag) { await api.batchTags([...selected.value], [tag.id], 'add'); selected.value = new Set(); await Promise.all([load(page.value.page), loadFacets()]) }
async function removeTag(tag: Tag) { await api.batchTags([...selected.value], [tag.id], 'remove'); selected.value = new Set(); await Promise.all([load(page.value.page), loadFacets()]) }
async function addCollection(collection: Collection) {
  const current = await api.libraryMedia(new URLSearchParams({ collection_id: collection.id, page_size: '100' }))
  await api.setCollectionItems(collection.id, [...new Set([...current.items.map(x => x.id), ...selected.value])])
  selected.value = new Set(); await loadFacets()
}
async function addToWatchlist(item: MediaItem) { await api.addToWatchlist(item.id); emit('watchlistChanged') }
async function addSelectedToWatchlist() {
  await Promise.all([...selected.value].map(id => api.addToWatchlist(id)))
  selected.value = new Set(); emit('watchlistChanged')
}
async function createTag() { const name = window.prompt('新标签名称'); if (name) { await api.createTag(name); await loadFacets() } }
async function createCollection() { const name = window.prompt('新合集名称'); if (name) { await api.createCollection(name); await loadFacets() } }
async function editTag(tag: Tag) { const name = window.prompt('重命名标签', tag.name); if (name) { await api.renameTag(tag.id, name); await loadFacets() } }
async function removeTagDefinition(tag: Tag) { if (window.confirm(`删除标签“${tag.name}”？不会删除视频。`)) { await api.deleteTag(tag.id); if (tagId.value===tag.id) tagId.value=''; await loadFacets() } }
async function editCollection(item: Collection) { const name = window.prompt('重命名合集', item.name); if (name) { await api.renameCollection(item.id, name); await loadFacets() } }
async function removeCollection(item: Collection) { if (window.confirm(`删除合集“${item.name}”？不会删除视频。`)) { await api.deleteCollection(item.id); if (collectionId.value===item.id) collectionId.value=''; await loadFacets() } }
async function deleteSource(item: MediaItem) {
  if (item.kind === 'local' || !window.confirm(`彻底删除网络源“${item.name}”？`)) return
  await api.deleteSource(item.id); detail.value = null; await load(page.value.page); emit('changed'); emit('watchlistChanged'); emit('layoutChanged')
}
async function renameFile() {
  if (!detail.value || !fileActions.value?.can_rename) return
  fileBusy.value = true; fileError.value = ''
  try {
    detail.value = await api.renameMediaFile(detail.value.id, fileName.value)
    fileName.value = detail.value.original_name || detail.value.location.split('/').pop() || ''
    fileActions.value = await api.fileActions(detail.value.id)
    await load(page.value.page); emit('changed'); emit('watchlistChanged')
  } catch (error) { fileError.value = error instanceof Error ? error.message : String(error) }
  finally { fileBusy.value = false }
}
async function deleteLocalFile() {
  if (!detail.value || !fileActions.value?.delete_mode) return
  const item = detail.value, actions = fileActions.value
  const first = actions.delete_mode === 'torrent'
    ? `该视频属于一个下载任务。继续将删除整个任务、全部下载文件及 ${actions.affected_media} 个媒体记录，确定吗？`
    : `确定永久删除“${item.original_name || item.name}”吗？`
  if (!window.confirm(first) || !window.confirm('此操作无法恢复。请再次确认永久删除。')) return
  fileBusy.value = true; fileError.value = ''
  try {
    await api.deleteMediaFile(item.id)
    detail.value = null
    await load(page.value.page); emit('changed'); emit('watchlistChanged'); emit('layoutChanged')
  } catch (error) { fileError.value = error instanceof Error ? error.message : String(error) }
  finally { fileBusy.value = false }
}
function openSource(item?: MediaItem) {
  sourceForm.id = item?.id; sourceForm.name = item?.name || ''
  sourceForm.kind = item?.kind === 'hls' ? 'hls' : 'direct'; sourceForm.location = item?.location || ''
  sourceEditing.value = true
}
function editSourceFromDetail() { if (detail.value) openSource(detail.value); detail.value = null }
async function saveSource() {
  if (sourceForm.id) await api.updateSource(sourceForm.id, sourceForm)
  else await api.createSource(sourceForm)
  sourceEditing.value = false; await load(page.value.page); emit('changed'); emit('watchlistChanged')
}
async function scan() {
  const { job_id } = await api.scan()
  while (true) {
    scanJob.value = await api.scanStatus(job_id)
    if (['completed', 'failed'].includes(scanJob.value.status)) break
    await new Promise(resolve => window.setTimeout(resolve, 500))
  }
  await load(1); emit('changed'); emit('watchlistChanged')
}
function fmtTime(value?: number | null) { if (!value) return '—'; const h=Math.floor(value/3600),m=Math.floor(value%3600/60),s=Math.floor(value%60); return `${h?`${h}:`:''}${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` }
function fmtSize(value?: number | null) { return value ? `${(value/1024/1024).toFixed(value > 1024**3 ? 0 : 1)} MB` : '—' }
watch([tagId, collectionId, filter, sort], () => void load(1))
watch(query, () => { window.clearTimeout(queryTimer); queryTimer = window.setTimeout(() => void load(1), 250) })
watch(detail, async item => {
  fileActions.value = null; fileError.value = ''
  fileName.value = item?.original_name || item?.location.split('/').pop() || ''
  if (item?.kind === 'local') {
    try { fileActions.value = await api.fileActions(item.id) }
    catch (error) { fileError.value = error instanceof Error ? error.message : String(error) }
  }
})
onMounted(() => { void Promise.all([load(), loadFacets()]) })
</script>

<template>
  <section class="manager">
    <header class="manager-head"><div><small>MEDIA MANAGER</small><h1>视频文件管理</h1></div><div class="manager-actions">
      <button @click="openSource()">添加网络源</button><button @click="scan">{{ scanJob && !['completed','failed'].includes(scanJob.status) ? `${scanJob.processed}/${scanJob.total}` : '扫描媒体库' }}</button>
      <button class="primary" @click="emit('close')">返回视频墙</button></div></header>
    <div class="manager-body">
      <aside class="manager-sidebar">
        <button :class="{active:section==='media'&&filter==='all'}" @click="section='media';filter='all'">全部视频 <i>{{ page.total }}</i></button>
        <button :class="{active:section==='media'&&filter==='favorite'}" @click="section='media';filter='favorite'">★ 收藏</button>
        <button :class="{active:section==='media'&&filter==='completed'}" @click="section='media';filter='completed'">✓ 已看完</button>
        <button :class="{active:section==='media'&&filter==='missing'}" @click="section='media';filter='missing'">! 文件不可用</button>
        <h3>标签 <button @click="createTag">＋</button></h3>
        <div v-for="tag in tags" :key="tag.id" class="facet-row" :class="{active:section==='media'&&tagId===tag.id}"><button @click="section='media';tagId=tagId===tag.id?'':tag.id">{{ tag.name }} <i>{{ tag.count }}</i></button><button title="重命名" @click="editTag(tag)">✎</button><button title="删除" @click="removeTagDefinition(tag)">×</button></div>
        <h3>合集 <button @click="createCollection">＋</button></h3>
        <div v-for="item in collections" :key="item.id" class="facet-row" :class="{active:section==='media'&&collectionId===item.id}"><button @click="section='media';collectionId=collectionId===item.id?'':item.id">{{ item.name }} <i>{{ item.count }}</i></button><button title="重命名" @click="editCollection(item)">✎</button><button title="删除" @click="removeCollection(item)">×</button></div>
        <button class="download-nav" :class="{ active: section === 'downloads' }" @click="section='downloads'"><span>⇩ 磁力下载</span><i>›</i></button>
        <button class="import-nav" :class="{ active: section === 'import' }" @click="section='import'"><span>＋ 视频移入</span><i>›</i></button>
      </aside>
      <main v-if="section === 'media'" class="manager-content">
        <div class="manager-tools"><input v-model.trim="query" placeholder="搜索标题、文件名、路径或备注…"><select v-model="sort"><option value="imported_desc">最近导入</option><option value="name_asc">名称升序</option><option value="modified_desc">最近修改</option><option value="duration_desc">时长最长</option><option value="size_desc">文件最大</option></select><button @click="view=view==='grid'?'table':'grid'">{{ view==='grid'?'表格':'网格' }}</button></div>
        <div v-if="selectedCount" class="bulk-bar">已选 {{ selectedCount }} 项 <button class="primary" @click="addSelectedToWatchlist">加入想看</button><span>标签：</span><template v-for="tag in tags" :key="tag.id"><button @click="addTag(tag)">＋{{ tag.name }}</button><button @click="removeTag(tag)">－{{ tag.name }}</button></template><span>加入合集：</span><button v-for="c in collections" :key="c.id" @click="addCollection(c)">{{ c.name }}</button></div>
        <div v-if="error" class="manager-empty">{{ error }}<button @click="load(page.page)">重试</button></div>
        <div v-else-if="loading" class="manager-empty">正在加载媒体库…</div>
        <div v-else-if="!page.items.length" class="manager-empty">没有符合条件的视频</div>
        <div v-else class="media-browser" :class="view">
          <article v-for="item in page.items" :key="item.id" :class="{selected:selected.has(item.id),missing:!item.available}" @click="toggle(item.id)" @dblclick="detail=item">
            <div class="poster"><img v-if="item.thumbnail_url" :src="item.thumbnail_url"><span v-else>▶</span><b>{{ fmtTime(item.duration) }}</b><i v-if="item.favorite">★</i></div>
            <div class="media-meta"><strong>{{ item.name }}</strong><small>{{ item.width ? `${item.width}×${item.height}` : '待分析' }} · {{ fmtSize(item.file_size) }}</small><small>{{ item.location }}</small></div>
            <div class="card-actions"><button :disabled="watchlistSet.has(item.id)" @click.stop="addToWatchlist(item)">{{ watchlistSet.has(item.id) ? '已加入' : '加入想看' }}</button><button @click.stop="detail=item">详情</button></div>
          </article>
        </div>
        <footer class="pager"><button :disabled="page.page<=1" @click="load(page.page-1)">上一页</button><span>{{ page.page }} / {{ page.pages }} · 共 {{ page.total }} 个</span><button :disabled="page.page>=page.pages" @click="load(page.page+1)">下一页</button></footer>
      </main>
      <DownloadManager v-else-if="section === 'downloads'" embedded @media-changed="emit('changed')" @watchlist-changed="emit('watchlistChanged')" />
      <MediaImporter v-else @changed="load(1);emit('changed')" @watchlist-changed="emit('watchlistChanged')" />
    </div>
    <form v-if="detail" class="detail-panel" @submit.prevent="saveDetail"><header><strong>视频详情</strong><button type="button" @click="detail=null">×</button></header><label>显示标题<input v-model.trim="detail.name" required></label><label>备注<textarea v-model="detail.notes" rows="5"></textarea></label><label>评分<select v-model="detail.rating"><option :value="null">未评分</option><option v-for="n in 5" :key="n" :value="n">{{ n }} 星</option></select></label><label><input v-model="detail.favorite" type="checkbox"> 收藏</label><label><input v-model="detail.completed" type="checkbox"> 已看完</label><p>{{ detail.location }}<br>{{ detail.video_codec || '—' }} / {{ detail.audio_codec || '—' }}</p><button class="primary">保存资料</button><template v-if="detail.kind === 'local'"><div class="file-divider"></div><label>磁盘文件名<input v-model.trim="fileName" :disabled="!fileActions?.can_rename || fileBusy" maxlength="255"></label><small v-if="fileActions?.reason" class="file-reason">{{ fileActions.reason }}</small><small v-if="fileError" class="file-error">{{ fileError }}</small><button type="button" :disabled="!fileActions?.can_rename || fileBusy" @click="renameFile">修改真实文件名</button><button type="button" class="danger-button" :disabled="!fileActions?.delete_mode || fileBusy" @click="deleteLocalFile">{{ fileActions?.delete_mode === 'torrent' ? '删除整个下载任务及文件' : fileActions?.delete_mode === 'record_only' ? '清理缺失视频记录' : '永久删除视频文件' }}</button></template><button v-if="detail.kind !== 'local'" type="button" @click="editSourceFromDetail">编辑网络源</button><button v-if="detail.kind !== 'local'" type="button" class="danger-button" @click="deleteSource(detail)">删除网络源</button></form>
    <form v-if="sourceEditing" class="detail-panel" @submit.prevent="saveSource"><header><strong>{{ sourceForm.id ? '编辑网络源' : '添加网络源' }}</strong><button type="button" @click="sourceEditing=false">×</button></header><label>名称<input v-model.trim="sourceForm.name" required maxlength="200"></label><label>类型<select v-model="sourceForm.kind"><option value="direct">视频直链</option><option value="hls">HLS（m3u8）</option></select></label><label>地址<input v-model.trim="sourceForm.location" type="url" required placeholder="https://…"></label><button class="primary">保存网络源</button></form>
  </section>
</template>
