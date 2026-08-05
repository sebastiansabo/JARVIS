import { createContext, useContext } from 'react'

// A DOM node exposed by the Hub breadcrumb (HubCrumb) into which an active
// module may portal its own toolbar, so the controls sit INLINE with the
// "‹ Hub / <Module>" title row instead of on a separate line below it. null when
// no slot is mounted (e.g. a panel rendered standalone in a test) → callers fall
// back to rendering their toolbar in normal flow.
export const HubHeaderSlotContext = createContext<HTMLElement | null>(null)
export const useHubHeaderSlot = () => useContext(HubHeaderSlotContext)
