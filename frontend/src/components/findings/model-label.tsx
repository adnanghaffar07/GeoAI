import { TEST_DETECTOR_LABEL, TRIAL_MODEL_LABEL } from '@/api/analysis'
import { cn } from '@/lib/utils'

interface ModelLabelProps {
  testDetector?: boolean
  trialModel?: boolean
  className?: string
  as?: 'p' | 'span'
}

/**
 * The warning shown on every AI result that does not come from an approved model:
 * the TEST DETECTOR (made-up results) or a TRIAL MODEL (real model, accuracy not approved).
 */
export function ModelLabel({ testDetector, trialModel, className, as: Tag = 'p' }: ModelLabelProps) {
  const text = testDetector ? TEST_DETECTOR_LABEL : trialModel ? TRIAL_MODEL_LABEL : null
  if (!text) return null
  return (
    <Tag
      className={cn('text-[0.7rem] font-semibold tracking-wide text-amber-800 uppercase', className)}
      title={trialModel ? 'This AI model has not passed its accuracy check. It misses much of the damage; a person must check every photo.' : undefined}
    >
      {text}
    </Tag>
  )
}
