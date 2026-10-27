import { WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'

import { logger } from '@/lib/logger'
import { notify } from '@/lib/notify'

/** A strip at the top while the device has no internet connection, so failed saves make sense. */
export function OfflineBanner() {
  const [online, setOnline] = useState(() => navigator.onLine)

  useEffect(() => {
    const goOnline = () => {
      setOnline(true)
      logger.info('Back online')
      notify.success('You are back online.')
    }
    const goOffline = () => {
      setOnline(false)
      logger.warn('Connection lost')
    }
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  if (online) return null
  return (
    <div role="alert" className="sticky top-0 z-[55] flex items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-center text-sm font-medium text-amber-950">
      <WifiOff className="size-4 shrink-0" aria-hidden />
      No internet connection. You can look around, but changes cannot be saved until you are back online.
    </div>
  )
}
