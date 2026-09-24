import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MediaImporter from './MediaImporter.vue'

const mocks = vi.hoisted(() => ({ importMedia: vi.fn(), scan: vi.fn(), scanStatus: vi.fn() }))
vi.mock('../api', () => ({ api: mocks }))

describe('MediaImporter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.importMedia.mockImplementation(async (file: File, progress: (value: number) => void) => {
      progress(50); progress(100)
      return { original_name: file.name, saved_name: file.name, relative_path: file.name, size: file.size }
    })
    mocks.scan.mockResolvedValue({ job_id: 'scan-1' })
    mocks.scanStatus.mockResolvedValue({ id: 'scan-1', status: 'completed', total: 2, processed: 2, errors: 0, message: '完成' })
  })

  it('uploads selected files sequentially and scans once', async () => {
    const wrapper = mount(MediaImporter)
    const input = wrapper.get('input[type=file]')
    const files = [new File(['one'], 'one.mp4', { type: 'video/mp4' }), new File(['two'], 'two.mkv')]
    Object.defineProperty(input.element, 'files', { value: files, configurable: true })
    await input.trigger('change')
    expect(wrapper.text()).toContain('one.mp4')
    await wrapper.findAll('button').find(button => button.text() === '开始移入')!.trigger('click')
    await flushPromises()
    expect(mocks.importMedia).toHaveBeenCalledTimes(2)
    expect(mocks.scan).toHaveBeenCalledOnce()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.text()).toContain('完成')
  })

  it('keeps processing after one file fails', async () => {
    mocks.importMedia.mockRejectedValueOnce(new Error('格式错误')).mockResolvedValueOnce({ original_name: 'ok.mp4', saved_name: 'ok.mp4', relative_path: 'ok.mp4', size: 1 })
    const wrapper = mount(MediaImporter)
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'bad.mp4'), new File(['y'], 'ok.mp4')], configurable: true })
    await input.trigger('change')
    await wrapper.findAll('button').find(button => button.text() === '开始移入')!.trigger('click')
    await flushPromises()
    expect(mocks.importMedia).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('格式错误')
    expect(mocks.scan).toHaveBeenCalledOnce()
  })
})
