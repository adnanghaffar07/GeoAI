import { describe, expect, it } from 'vitest'

import { boxStyle } from '@/lib/bbox'

describe('boxStyle', () => {
  it('turns a pixel box into percentages of the photo', () => {
    expect(boxStyle([100, 75, 300, 150], 400, 300)).toEqual({ left: '25%', top: '25%', width: '50%', height: '25%' })
  })

  it('covers the whole photo for a full-size box', () => {
    expect(boxStyle([0, 0, 4000, 3000], 4000, 3000)).toEqual({ left: '0%', top: '0%', width: '100%', height: '100%' })
  })
})
