import { describe, expect, it, vi } from 'vitest'
import { toggleFullscreen } from './fullscreen'

describe('toggleFullscreen', () => {
  it('requests fullscreen for the video wall', async () => {
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    const element = { requestFullscreen } as unknown as HTMLElement
    const doc = { fullscreenElement: null } as Document
    await toggleFullscreen(element, doc)
    expect(requestFullscreen).toHaveBeenCalledOnce()
  })

  it('exits fullscreen when the video wall is already fullscreen', async () => {
    const element = {} as HTMLElement
    const exitFullscreen = vi.fn().mockResolvedValue(undefined)
    const doc = { fullscreenElement: element, exitFullscreen } as unknown as Document
    await toggleFullscreen(element, doc)
    expect(exitFullscreen).toHaveBeenCalledOnce()
  })

  it('reports unsupported browsers', async () => {
    const element = {} as HTMLElement
    const doc = { fullscreenElement: null } as Document
    await expect(toggleFullscreen(element, doc)).rejects.toThrow('当前浏览器不支持视频墙全屏')
  })
})

