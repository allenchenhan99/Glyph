import type {
  ResearchMap,
  ResearchMapJob,
  ResearchNode,
  ResearchNodeReview
} from './types'

export type ResearchMapNotice = { kind: 'status' | 'error'; message: string } | null

type PendingReview = {
  requestId: string
  nodeId: string
  previousNode: ResearchNode
}

export type ResearchMapState = {
  loadStatus: 'idle' | 'loading' | 'ready' | 'error'
  map: ResearchMap | null
  job: ResearchMapJob | null
  polling: boolean
  mapRefreshNonce: number
  selectedNodeId: string | null
  guidedStep: number
  inspectorOpen: boolean
  readerFocusBlockId: string | null
  pendingReview: PendingReview | null
  mapWarnings: { partial: boolean; stale: boolean }
  notice: ResearchMapNotice
}

export const initialResearchMapState: ResearchMapState = {
  loadStatus: 'idle',
  map: null,
  job: null,
  polling: false,
  mapRefreshNonce: 0,
  selectedNodeId: null,
  guidedStep: 0,
  inspectorOpen: false,
  readerFocusBlockId: null,
  pendingReview: null,
  mapWarnings: { partial: false, stale: false },
  notice: null
}

export type ResearchMapAction =
  | { type: 'resetWorkspace' }
  | { type: 'mapLoading' }
  | { type: 'mapLoaded'; map: ResearchMap }
  | { type: 'mapAbsent' }
  | { type: 'mapFailed'; message: string }
  | { type: 'jobUpdated'; job: ResearchMapJob }
  | { type: 'selectNode'; nodeId: string }
  | { type: 'openInspector' }
  | { type: 'closeInspector' }
  | { type: 'guidedNext' }
  | { type: 'guidedPrevious' }
  | { type: 'reviewOptimistic'; requestId: string; nodeId: string; review: ResearchNodeReview }
  | { type: 'reviewSaved'; requestId: string; nodeId: string; review: ResearchNodeReview }
  | { type: 'reviewConflict'; requestId: string; message: string }
  | { type: 'openReader'; blockId: string }
  | { type: 'returnToMap' }

export function researchMapReducer(
  state: ResearchMapState,
  action: ResearchMapAction
): ResearchMapState {
  switch (action.type) {
    case 'resetWorkspace':
      return initialResearchMapState
    case 'mapLoading':
      return { ...state, loadStatus: 'loading', notice: null }
    case 'mapLoaded':
      return {
        ...state,
        loadStatus: 'ready',
        map: action.map,
        selectedNodeId: state.selectedNodeId ?? action.map.nodes[0]?.id ?? null,
        inspectorOpen: true,
        mapWarnings: {
          partial: action.map.status === 'partial',
          stale: action.map.is_stale
        },
        notice: null
      }
    case 'mapAbsent':
      return {
        ...state,
        loadStatus: 'ready',
        map: null,
        selectedNodeId: null,
        inspectorOpen: false,
        mapWarnings: { partial: false, stale: false },
        notice: null
      }
    case 'mapFailed':
      return {
        ...state,
        loadStatus: 'error',
        notice: { kind: 'error', message: action.message }
      }
    case 'jobUpdated': {
      const terminal = action.job.status === 'completed' || action.job.status === 'failed'
      const newlyCompleted =
        action.job.status === 'completed' && state.job?.status !== 'completed'
      return {
        ...state,
        job: action.job,
        polling: !terminal,
        mapRefreshNonce: state.mapRefreshNonce + (newlyCompleted ? 1 : 0),
        notice:
          action.job.status === 'failed'
            ? {
                kind: 'error',
                message: action.job.error_message ?? 'Research Map generation failed.'
              }
            : state.notice
      }
    }
    case 'selectNode':
      return { ...state, selectedNodeId: action.nodeId }
    case 'openInspector':
      return { ...state, inspectorOpen: true }
    case 'closeInspector':
      return { ...state, inspectorOpen: false }
    case 'guidedNext':
      return { ...state, guidedStep: Math.min(4, state.guidedStep + 1) }
    case 'guidedPrevious':
      return { ...state, guidedStep: Math.max(0, state.guidedStep - 1) }
    case 'reviewOptimistic': {
      const previousNode = state.map?.nodes.find((node) => node.id === action.nodeId)
      if (!state.map || !previousNode) return state
      return {
        ...state,
        map: replaceNode(state.map, action.nodeId, action.review),
        pendingReview: { requestId: action.requestId, nodeId: action.nodeId, previousNode },
        notice: null
      }
    }
    case 'reviewSaved':
      if (!state.map || state.pendingReview?.requestId !== action.requestId) return state
      {
        const isFirstCoreReview =
          state.pendingReview?.nodeId === action.nodeId &&
          state.pendingReview.previousNode.review === null &&
          coreReviewNodeTypes.has(state.pendingReview.previousNode.node_type)
        const reviewedMap = replaceNode(state.map, action.nodeId, action.review)
        return {
          ...state,
          map: {
            ...reviewedMap,
            reviewed_core_nodes: isFirstCoreReview
              ? Math.min(
                  reviewedMap.reviewable_core_nodes,
                  reviewedMap.reviewed_core_nodes + 1
                )
              : reviewedMap.reviewed_core_nodes
          },
          pendingReview: null,
          notice: { kind: 'status', message: 'Review saved.' }
        }
      }
    case 'reviewConflict': {
      if (!state.map || state.pendingReview?.requestId !== action.requestId) return state
      const restoredNodes = state.map.nodes.map((node) =>
        node.id === state.pendingReview?.nodeId ? state.pendingReview.previousNode : node
      )
      return {
        ...state,
        map: { ...state.map, nodes: restoredNodes },
        pendingReview: null,
        notice: { kind: 'error', message: action.message }
      }
    }
    case 'openReader':
      return { ...state, readerFocusBlockId: action.blockId }
    case 'returnToMap':
      return { ...state, readerFocusBlockId: null }
  }
}

const coreReviewNodeTypes = new Set<ResearchNode['node_type']>([
  'research_question',
  'author_claim',
  'hypothesis',
  'data_and_sample',
  'data_source',
  'sample_filter',
  'signal_definition',
  'variable_definition',
  'portfolio_construction',
  'rebalancing_rule',
  'empirical_method',
  'benchmark_model',
  'identification_strategy',
  'primary_result',
  'statistical_evidence',
  'economic_magnitude',
  'limitations',
  'implementation_constraint',
  'alternative_explanation'
])

function replaceNode(
  map: ResearchMap,
  nodeId: string,
  review: ResearchNodeReview
): ResearchMap {
  return {
    ...map,
    nodes: map.nodes.map((node) =>
      node.id === nodeId
        ? {
            ...node,
            review,
            effective_claim_text:
              review.status === 'corrected' && review.corrected_claim_text
                ? review.corrected_claim_text
                : node.claim_text
          }
        : node
    )
  }
}

type PollOptions = {
  fetchJob: (jobId: string) => Promise<ResearchMapJob>
  onJob: (job: ResearchMapJob) => void
  signal?: AbortSignal
  intervalMs?: number
  waitForNextPoll?: (intervalMs: number, signal?: AbortSignal) => Promise<void>
}

export async function pollResearchMapJob(
  jobId: string,
  options: PollOptions
): Promise<ResearchMapJob | null> {
  const waitForNextPoll = options.waitForNextPoll ?? waitForDelay
  while (!options.signal?.aborted) {
    let job: ResearchMapJob
    try {
      job = await options.fetchJob(jobId)
    } catch (error) {
      if (options.signal?.aborted) return null
      throw error
    }
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
