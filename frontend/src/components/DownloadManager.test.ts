import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DownloadManager from './DownloadManager.vue'

const mocks = vi.hoisted(() => ({
  downloadStatus: vi.fn(), downloads: vi.fn(), addDownload: vi.fn(), pauseDownload: vi.fn(),
  resumeDownload: vi.fn(), deleteDownload: vi.fn(), addToWatchlist: vi.fn(),
}))
vi.mock('../api', () => ({ api: mocks }))

describe('DownloadManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.downloadStatus.mockResolvedValue({ connected: true, version: '5.2.3', download_speed: 0, upload_speed: 0 })
    mocks.downloads.mockResolvedValue([])
    mocks.addDownload.mockResolvedValue({ hash: 'a'.repeat(40) })
  })
  it('submits a magnet link and shows empty state', async () => {
    const wrapper = mount(DownloadManager)
    await vi.waitFor(() => expect(wrapper.text()).toContain('暂无下载任务'))
    await wrapper.get('input').setValue(`magnet:?xt=urn:btih:${'a'.repeat(40)}`)
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(mocks.addDownload).toHaveBeenCalledOnce())
    wrapper.unmount()
  })
  it('shows a disconnected reason', async () => {
    mocks.downloadStatus.mockResolvedValue({ connected: false, download_speed: 0, upload_speed: 0, error: '未配置认证' })
    const wrapper = mount(DownloadManager)
    await vi.waitFor(() => expect(wrapper.text()).toContain('未配置认证'))
    wrapper.unmount()
  })
})
