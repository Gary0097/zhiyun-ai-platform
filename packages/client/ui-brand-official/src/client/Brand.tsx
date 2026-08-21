import { IconSparkle16 } from '@deepseek-ai/dsh-client-ui-primitives'
import type { HeroBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { SidebarBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'

type OfficialBrandMarkProps = HeroBrandMarkOwnerProps & SidebarBrandMarkOwnerProps

/**
 * Render the neutral mark with the presentation requested by its host surface.
 * @param props - Host-supplied mark presentation.
 * @returns the neutral sparkle mark.
 */
export function OfficialBrandMark({ size, className }: OfficialBrandMarkProps) {
  return <IconSparkle16 size={size} className={className} />
}

/**
 * Render the neutral product name without its independently slotted mark.
 * @returns the neutral name text.
 */
export function OfficialBrandName() {
  return <span>AI</span>
}
