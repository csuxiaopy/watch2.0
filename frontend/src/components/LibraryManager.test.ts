import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LibraryManager from './LibraryManager.vue'

const sample = {
  id: 'video-1', name: '示例视频.mp4', kind: 'local' as const, location: '课程/示例视频.mp4',
  available: true, playback_url: '/api/files/video-1', favorite: false, notes: '', watch_count: 0,
  playback_position: 0, completed: false, thumbnail_status: 'ready', thumbnail_url: '/thumb.jpg',
  duration: 90, width: 1920, height: 1080, file_size: 1024, tags: [],
}
const mocks = vi.hoisted(() => ({
  libraryMedia: vi.fn(), tags: vi.fn(), collections: vi.fn(), updateMedia: vi.fn(),
  scan: vi.fn(), scanStatus: vi.fn(), batchTags: vi.fn(), setCollectionItems: vi.fn(),
  createTag: vi.fn(), createCollection: vi.fn(),
  renameTag: vi.fn(), deleteTag: vi.fn(), renameCollection: vi.fn(), deleteCollection: vi.fn(),
  addToWatchlist: vi.fn(), createSource: vi.fn(), updateSource: vi.fn(), deleteSource: vi.fn(),
  fileActions: vi.fn(), renameMediaFile: vi.fn(), deleteMediaFile: vi.fn(),
}))
vi.mock('../api', () => ({ api: mocks }))

describe('LibraryManager', () => {
  beforeEach(() => {
    mocks.libraryMedia.mockResolvedValue({ items: [sample], page: 1, page_size: 48, total: 1, pages: 1 })
    mocks.tags.mockResolvedValue([]); mocks.collections.mockResolvedValue([])
    mocks.fileActions.mockResolvedValue({ local: true, can_rename: true, delete_mode: 'single_file', affected_media: 1, reason: null })
    mocks.renameMediaFile.mockResolvedValue({ ...sample, name: 'renamed.mp4', original_name: 'renamed.mp4', location: '课程/renamed.mp4' })
    mocks.deleteMediaFile.mockResolvedValue({ deleted_media_ids: [sample.id], deleted_files: [sample.location], torrent_hash: null })
  })

  it('loads media and sends a selected video to the wall', async () => {
    const wrapper = mount(LibraryManager, { props: { watchlistIds: [] } })
    await flushPromises()
    expect(wrapper.text()).toContain('示例视频.mp4')
    expect(wrapper.text()).toContain('1920×1080')
    await wrapper.findAll('button').find(button => button.text() === '加入想看')!.trigger('click')
    expect(mocks.addToWatchlist).toHaveBeenCalledWith(sample.id)
    expect(wrapper.emitted('watchlistChanged')).toHaveLength(1)
  })

  it('debounces search and exposes grid/table switching', async () => {
    const wrapper = mount(LibraryManager, { props: { watchlistIds: [] } })
    await flushPromises()
    await wrapper.get('input[placeholder*="搜索标题"]').setValue('课程')
    await new Promise(resolve => setTimeout(resolve, 300)); await flushPromises()
    expect(mocks.libraryMedia).toHaveBeenLastCalledWith(expect.objectContaining({}))
    await wrapper.findAll('button').find(button => button.text() === '表格')!.trigger('click')
    expect(wrapper.get('.media-browser').classes()).toContain('table')
  })

  it('shows downloads inside the media manager content area', async () => {
    const wrapper = mount(LibraryManager, { props: { watchlistIds: [] } })
    await flushPromises()
    await wrapper.get('.download-nav').trigger('click')
    expect(wrapper.find('.download-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('磁力下载')
    expect(wrapper.find('.manager-sidebar').exists()).toBe(true)
  })

  it('shows media import below downloads inside the content area', async () => {
    const wrapper = mount(LibraryManager, { props: { watchlistIds: [] } })
    await flushPromises()
    await wrapper.get('.import-nav').trigger('click')
    expect(wrapper.find('.import-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('打开文件选择器')
    expect(wrapper.find('.manager-sidebar').exists()).toBe(true)
  })

  it('renames and permanently deletes a local video from details', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(LibraryManager, { props: { watchlistIds: [] } })
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '详情')!.trigger('click')
    await flushPromises()
    await wrapper.get('input[maxlength="255"]').setValue('renamed.mp4')
    await wrapper.findAll('button').find(button => button.text() === '修改真实文件名')!.trigger('click')
    await flushPromises()
    expect(mocks.renameMediaFile).toHaveBeenCalledWith(sample.id, 'renamed.mp4')
    await wrapper.findAll('button').find(button => button.text() === '永久删除视频文件')!.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(mocks.deleteMediaFile).toHaveBeenCalledWith(sample.id)
    expect(wrapper.emitted('layoutChanged')).toHaveLength(1)
    confirm.mockRestore()
  })
})
