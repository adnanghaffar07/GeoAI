import { ImageOff } from 'lucide-react'
import { useState } from 'react'

import type { Finding } from '@/api/findings'
import { originalUrl, previewUrl } from '@/api/images'
import { boxStyle } from '@/lib/bbox'
import { cn } from '@/lib/utils'

interface FindingPhotoProps {
  finding: Finding
  /** Show the AI's box (reviewers can turn it off to see the surface underneath). */
  showBox?: boolean
  /** 1 = fit the width; larger values zoom in (the frame scrolls). */
  zoom?: number
  /** Use the full-size original (review screen) instead of the small preview. */
  original?: boolean
  className?: string
}

/** The finding's photo with the AI box drawn at the right place at any size or zoom. */
export function FindingPhoto({ finding, showBox = true, zoom = 1, original = false, className }: FindingPhotoProps) {
  const [failed, setFailed] = useState(false)
  const photo = finding.photo
  if (!photo) {
    return (
      <div className={cn('flex aspect-[4/3] flex-col items-center justify-center gap-1 bg-asphalt-100 text-xs text-asphalt-500', className)}>
        <ImageOff className="size-5" aria-hidden />
        No photo attached
      </div>
    )
  }
  return (
    <div className={cn('overflow-auto bg-asphalt-900', className)}>
      {/* Same shape as the original photo, so the box percentages line up with the picture. */}
      <div className="relative" style={{ width: `${zoom * 100}%`, aspectRatio: `${photo.width_px} / ${photo.height_px}` }}>
        {failed ? (
          <span className="absolute inset-0 flex items-center justify-center text-xs text-asphalt-200">Photo not available</span>
        ) : (
          <img
            src={original ? originalUrl(photo.id) : previewUrl(photo.id)}
            alt={`Photo ${photo.original_filename}`}
            className="size-full object-fill"
            onError={() => setFailed(true)}
          />
        )}
        {showBox && finding.predicted_bbox && (
          <div
            data-testid="finding-box"
            className="pointer-events-none absolute rounded-sm border-2 border-lane-400 shadow-[0_0_0_1px_rgba(0,0,0,0.6)]"
            style={boxStyle(finding.predicted_bbox, photo.width_px, photo.height_px)}
            aria-hidden
          />
        )}
      </div>
    </div>
  )
}
