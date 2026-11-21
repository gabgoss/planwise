// The plugin's own contract: the values it keeps in `$.state` under the name `planwise`.
// It adds no noun to `$`.
export type PlanwiseLastDraft = {
  draftId: string
  kind: 'bug' | 'lesson' | 'idea'
  title: string
  preview: string
  feedbackDir: string
  sessionId: string
  configPath: string
}

/** What the update card offers. `NEEDS_CONFIRM` follows an Update Now press whose update needs a terminal. */
export type PlanwiseUpdateOffer = {
  verdict: 'RESTART' | 'PLUGIN_BEHIND' | 'PROJECT_BEHIND' | 'NEEDS_CONFIRM'
  running: string | null
  installed: string | null
  latest: string | null
  pin: string | null
  confirmCommand: string | null
}

declare module 'claude-code' {
  interface PluginState {
    planwise: {
      lastDraft: PlanwiseLastDraft | null
      cardsShown: number
      dismissals: number
      hidden: boolean
      posting: boolean
      updateOffer: PlanwiseUpdateOffer | null
      updateHidden: boolean
      updateBusy: boolean
    }
  }
}
