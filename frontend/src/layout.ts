import type { Layout } from './types'

export function focusSlot(layout: Layout, slotId: number): boolean {
  const target = layout.slots.find(slot => slot.slot_id === slotId)
  const current = layout.slots.find(slot => slot.position === 'main')
  if (!target || !current || target === current) return false
  const targetPosition = target.position
  target.position = 'main'
  current.position = targetPosition
  target.muted = false
  current.muted = true
  return true
}

