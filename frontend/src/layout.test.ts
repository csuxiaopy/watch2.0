import { describe, expect, it } from 'vitest'
import { focusSlot } from './layout'
import type { Layout } from './types'

function layout(): Layout {
  return {
    slots: Array.from({ length: 13 }, (_, slot_id) => ({
      slot_id,
      position: slot_id === 0 ? 'main' : `p${slot_id - 1}`,
      media_id: `video-${slot_id}`,
      muted: slot_id !== 0,
      volume: 1,
      playing: true,
    })),
  }
}

describe('focusSlot', () => {
  it('swaps the main and peripheral positions without changing media assignments', () => {
    const value = layout()
    const assignments = value.slots.map(slot => slot.media_id)
    expect(focusSlot(value, 5)).toBe(true)
    expect(value.slots[5].position).toBe('main')
    expect(value.slots[0].position).toBe('p4')
    expect(value.slots[5].muted).toBe(false)
    expect(value.slots[0].muted).toBe(true)
    expect(value.slots.map(slot => slot.media_id)).toEqual(assignments)
  })

  it('does nothing when the selected slot is already main', () => {
    const value = layout()
    expect(focusSlot(value, 0)).toBe(false)
    expect(value.slots[0].position).toBe('main')
  })
})

