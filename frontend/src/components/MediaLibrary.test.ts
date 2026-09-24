import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MediaLibrary from './MediaLibrary.vue'

const item = (id: string, name: string) => ({ id, name, kind: 'local' as const, location: `${name}.mp4`,
  available: true, playback_url: `/api/files/${id}`, favorite: false, notes: '', watch_count: 0,
  playback_position: 0, completed: false, thumbnail_status: 'ready', tags: [] })

describe('MediaLibrary watchlist', () => {
  it('assigns, removes and reorders without deleting media', async () => {
    const items = [item('1', '第一集'), item('2', '第二集')]
    const wrapper = mount(MediaLibrary, { props: { media: items, selectedId: null } })
    await wrapper.findAll('.media-row')[0].trigger('click')
    expect(wrapper.emitted('assign')?.[0]?.[0]).toEqual(items[0])
    await wrapper.findAll('.row-tools .danger')[0].trigger('click')
    expect(wrapper.emitted('remove')?.[0]?.[0]).toEqual(items[0])
    await wrapper.findAll('.row-tools i')[1].trigger('click')
    expect(wrapper.emitted('move')?.[0]).toEqual([0, 1])
  })

  it('shows an actionable empty state', () => {
    const wrapper = mount(MediaLibrary, { props: { media: [], selectedId: null } })
    expect(wrapper.text()).toContain('请前往“管理媒体库”添加想看的视频')
  })
})
