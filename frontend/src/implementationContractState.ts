import type {
  ContractResolution,
  ImplementationContract,
  ImplementationContractItem,
  ImplementationContractJob
} from './types'

export type ContractNotice = { kind: 'status' | 'error'; message: string } | null
export type ContractReturnSurface = 'contract' | null

type PendingResolution = {
  requestId: string
  itemId: string
  previousItem: ImplementationContractItem
}

export type ImplementationContractState = {
  activeDocumentId: string | null
  loadStatus: 'idle' | 'loading' | 'absent' | 'ready' | 'error'
  contract: ImplementationContract | null
  job: ImplementationContractJob | null
  polling: boolean
  contractRefreshNonce: number
  selectedItemId: string | null
  guidedStep: number
  inspectorOpen: boolean
  readerFocusBlockId: string | null
  returnSurface: ContractReturnSurface
  pendingResolution: PendingResolution | null
  contractWarnings: { stale: boolean; blocked: boolean; blockerCount: number }
  notice: ContractNotice
}

export const initialImplementationContractState: ImplementationContractState = {
  activeDocumentId: null,
  loadStatus: 'idle',
  contract: null,
  job: null,
  polling: false,
  contractRefreshNonce: 0,
  selectedItemId: null,
  guidedStep: 0,
  inspectorOpen: false,
  readerFocusBlockId: null,
  returnSurface: null,
  pendingResolution: null,
  contractWarnings: { stale: false, blocked: false, blockerCount: 0 },
  notice: null
}

export type ImplementationContractAction =
  | { type: 'resetDocument'; documentId: string }
  | { type: 'contractLoading'; documentId: string }
  | { type: 'contractLoaded'; documentId: string; contract: ImplementationContract }
  | { type: 'contractAbsent'; documentId: string }
  | { type: 'contractFailed'; documentId: string; message: string }
  | { type: 'jobUpdated'; documentId: string; job: ImplementationContractJob }
  | { type: 'selectItem'; itemId: string }
  | { type: 'openInspector' }
  | { type: 'closeInspector' }
  | { type: 'guidedNext' }
  | { type: 'guidedPrevious' }
  | {
      type: 'resolutionOptimistic'
      requestId: string
      itemId: string
      resolution: ContractResolution
    }
  | {
      type: 'resolutionSaved'
      requestId: string
      itemId: string
      resolution: ContractResolution
    }
  | { type: 'resolutionConflict'; requestId: string; message: string }
  | { type: 'openReader'; blockId: string }
  | { type: 'returnToContract' }

export function implementationContractReducer(
  state: ImplementationContractState,
  action: ImplementationContractAction
): ImplementationContractState {
  switch (action.type) {
    case 'resetDocument':
      return { ...initialImplementationContractState, activeDocumentId: action.documentId }
    case 'contractLoading':
      return {
        ...state,
        activeDocumentId: action.documentId,
        loadStatus: 'loading',
        notice: null
      }
    case 'contractLoaded':
      if (state.activeDocumentId !== action.documentId) return state
      return loadedState(state, action.contract)
    case 'contractAbsent':
      if (state.activeDocumentId !== action.documentId) return state
      return {
        ...state,
        loadStatus: 'absent',
        contract: null,
        selectedItemId: null,
        inspectorOpen: false,
        pendingResolution: null,
        contractWarnings: { stale: false, blocked: false, blockerCount: 0 },
        notice: null
      }
    case 'contractFailed':
      if (state.activeDocumentId !== action.documentId) return state
      return {
        ...state,
        loadStatus: 'error',
        notice: { kind: 'error', message: action.message }
      }
    case 'jobUpdated':
      if (
        state.activeDocumentId !== null &&
        state.activeDocumentId !== action.documentId
      ) {
        return state
      }
      return jobState(state, action.documentId, action.job)
    case 'selectItem':
      return selectItem(state, action.itemId)
    case 'openInspector':
      return { ...state, inspectorOpen: true }
    case 'closeInspector':
      return { ...state, inspectorOpen: false }
    case 'guidedNext':
      return { ...state, guidedStep: Math.min(5, state.guidedStep + 1) }
    case 'guidedPrevious':
      return { ...state, guidedStep: Math.max(0, state.guidedStep - 1) }
    case 'resolutionOptimistic':
      return optimisticResolution(state, action)
    case 'resolutionSaved':
      return savedResolution(state, action)
    case 'resolutionConflict':
      return resolutionConflict(state, action.requestId, action.message)
    case 'openReader':
      return {
        ...state,
        readerFocusBlockId: action.blockId,
        returnSurface: 'contract'
      }
    case 'returnToContract':
      return { ...state, readerFocusBlockId: null, returnSurface: null }
  }
}

function loadedState(
  state: ImplementationContractState,
  contract: ImplementationContract
): ImplementationContractState {
  const blockerCount = contract.issues.filter(
    (issue) => issue.severity === 'error'
  ).length
  const selectedExists = contract.items.some(
    (item) => item.id === state.selectedItemId
  )
  return {
    ...state,
    loadStatus: 'ready',
    contract,
    selectedItemId: selectedExists
      ? state.selectedItemId
      : (contract.items[0]?.id ?? null),
    inspectorOpen: contract.items.length > 0,
    pendingResolution: null,
    contractWarnings: {
      stale: contract.is_stale,
      blocked: contract.readiness === 'blocked',
      blockerCount
    },
    notice: null
  }
}

function jobState(
  state: ImplementationContractState,
  documentId: string,
  job: ImplementationContractJob
): ImplementationContractState {
  const terminal = job.status === 'completed' || job.status === 'failed'
  const newlyCompleted =
    job.status === 'completed' && state.job?.status !== 'completed'
  return {
    ...state,
    activeDocumentId: state.activeDocumentId ?? documentId,
    job,
    polling: !terminal,
    contractRefreshNonce:
      state.contractRefreshNonce + (newlyCompleted ? 1 : 0),
    notice:
      job.status === 'failed'
        ? {
            kind: 'error',
            message: job.error_message ?? 'Implementation Contract generation failed.'
          }
        : state.notice
  }
}

function selectItem(
  state: ImplementationContractState,
  itemId: string
): ImplementationContractState {
  if (!state.contract?.items.some((item) => item.id === itemId)) return state
  const restored =
    state.pendingResolution !== null && state.pendingResolution.itemId !== itemId
      ? rollbackPendingResolution(state)
      : state
  return { ...restored, selectedItemId: itemId }
}

function optimisticResolution(
  state: ImplementationContractState,
  action: Extract<ImplementationContractAction, { type: 'resolutionOptimistic' }>
): ImplementationContractState {
  if (
    !state.contract ||
    action.resolution.item_id !== action.itemId ||
    action.resolution.request_id !== action.requestId
  ) {
    return state
  }
  const previousItem = state.contract.items.find((item) => item.id === action.itemId)
  if (!previousItem) return state
  const validationMessage = resolutionValidationMessage(action.resolution)
  if (validationMessage !== null) {
    return {
      ...state,
      notice: { kind: 'error', message: validationMessage }
    }
  }
  return {
    ...state,
    contract: replaceItem(
      state.contract,
      applyResolution(previousItem, action.resolution, false)
    ),
    pendingResolution: {
      requestId: action.requestId,
      itemId: action.itemId,
      previousItem
    },
    notice: null
  }
}

function savedResolution(
  state: ImplementationContractState,
  action: Extract<ImplementationContractAction, { type: 'resolutionSaved' }>
): ImplementationContractState {
  const pending = state.pendingResolution
  if (
    !state.contract ||
    !pending ||
    pending.requestId !== action.requestId ||
    pending.itemId !== action.itemId ||
    state.selectedItemId !== action.itemId
  ) {
    return state
  }
  const item = state.contract.items.find((value) => value.id === action.itemId)
  if (!item) return state
  return {
    ...state,
    loadStatus: 'loading',
    contract: replaceItem(state.contract, applyResolution(item, action.resolution, true)),
    pendingResolution: null,
    contractRefreshNonce: state.contractRefreshNonce + 1,
    notice: { kind: 'status', message: 'Decision saved. Verifying readiness.' }
  }
}

function resolutionConflict(
  state: ImplementationContractState,
  requestId: string,
  message: string
): ImplementationContractState {
  if (state.pendingResolution?.requestId !== requestId) return state
  const restored = rollbackPendingResolution(state)
  return {
    ...restored,
    notice: { kind: 'error', message }
  }
}

function rollbackPendingResolution(
  state: ImplementationContractState
): ImplementationContractState {
  if (!state.contract || !state.pendingResolution) return state
  return {
    ...state,
    contract: replaceItem(state.contract, state.pendingResolution.previousItem),
    pendingResolution: null
  }
}

function applyResolution(
  item: ImplementationContractItem,
  resolution: ContractResolution,
  appendHistory: boolean
): ImplementationContractItem {
  const usesReplacement =
    resolution.status === 'corrected' || resolution.status === 'decided'
  const notApplicable = resolution.status === 'not_applicable'
  return {
    ...item,
    effective_value: usesReplacement
      ? resolution.resolved_value
      : notApplicable
        ? null
        : item.draft_value,
    effective_origin:
      usesReplacement || notApplicable ? 'human_decision' : item.origin,
    resolution,
    resolution_history: appendHistory
      ? [
          ...item.resolution_history.filter(
            (entry) => entry.request_id !== resolution.request_id
          ),
          resolution
        ]
      : item.resolution_history
  }
}

function replaceItem(
  contract: ImplementationContract,
  item: ImplementationContractItem
): ImplementationContract {
  return {
    ...contract,
    items: contract.items.map((value) => (value.id === item.id ? item : value))
  }
}

function resolutionValidationMessage(
  resolution: ContractResolution
): string | null {
  const hasReason = Boolean(resolution.reason?.trim())
  if (
    (resolution.status === 'corrected' || resolution.status === 'decided') &&
    (resolution.resolved_value === null || !hasReason)
  ) {
    return `A ${resolution.status} resolution requires a value and reason.`
  }
  if (
    resolution.status === 'not_applicable' &&
    (resolution.resolved_value !== null || !hasReason)
  ) {
    return 'A not_applicable resolution requires a reason and no value.'
  }
  if (
    (resolution.status === 'confirmed' || resolution.status === 'questioned') &&
    resolution.resolved_value !== null
  ) {
    return `A ${resolution.status} resolution must not have a replacement value.`
  }
  return null
}

type PollOptions = {
  fetchJob: (jobId: string) => Promise<ImplementationContractJob>
  onJob: (job: ImplementationContractJob) => void
  signal?: AbortSignal
  intervalMs?: number
  waitForNextPoll?: (intervalMs: number, signal?: AbortSignal) => Promise<void>
}

export async function pollImplementationContractJob(
  jobId: string,
  options: PollOptions
): Promise<ImplementationContractJob | null> {
  const waitForNextPoll = options.waitForNextPoll ?? waitForDelay
  while (!options.signal?.aborted) {
    let job: ImplementationContractJob
    try {
      job = await options.fetchJob(jobId)
    } catch (error) {
      if (options.signal?.aborted) return null
      throw error
    }
    if (options.signal?.aborted) return null
    options.onJob(job)
    if (job.status === 'completed' || job.status === 'failed') return job
    await waitForNextPoll(options.intervalMs ?? 750, options.signal)
  }
  return null
}

function waitForDelay(intervalMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve()
      return
    }
    const timeoutId = window.setTimeout(resolve, intervalMs)
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timeoutId)
        resolve()
      },
      { once: true }
    )
  })
}
