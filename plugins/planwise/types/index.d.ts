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

declare module 'claude-code' {
  interface PluginState {
    planwise: {
      lastDraft: PlanwiseLastDraft | null
      cardsShown: number
      dismissals: number
      hidden: boolean
    }
  }
}
