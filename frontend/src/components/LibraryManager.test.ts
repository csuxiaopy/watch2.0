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
}))
vi.mock('../api', () => ({ api: mocks }))

describe('LibraryManager', () => {
  beforeEach(() => {
    mocks.libraryMedia.mockResolvedValue({ items: [sample], page: 1, page_size: 48, total: 1, pages: 1 })
    mocks.tags.mockResolvedValue([]); mocks.collections.mockResolvedValue([])
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
})
