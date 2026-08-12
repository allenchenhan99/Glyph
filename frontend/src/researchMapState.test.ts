import { describe, expect, it, vi } from 'vitest'

import {
  initialResearchMapState,
  pollResearchMapJob,
  researchMapReducer
} from './researchMapState'
import type { ResearchMap, ResearchMapJob, ResearchNodeReview } from './types'

const review: ResearchNodeReview = {
  id: 'review-1',
  status: 'corrected',
  corrected_claim_text: 'Corrected claim',
  review_note: 'Checked against evidence.',
  revision_number: 1,
  supersedes_review_id: null,
  reviewed_at: '2026-08-12T12:00:00Z'
}

const map: ResearchMap = {
  id: 'map-1',
  document_id: 'doc-1',
  previous_version_id: null,
  source_content_hash: 'a'.repeat(64),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  is_active: true,
  is_current: false,
  is_stale: true,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
  reviewed_core_nodes: 0,
  reviewable_core_nodes: 1,
  nodes: [
    {
      id: 'node-1',
      parent_node_id: null,
      node_key: 'primary_result.1',
      node_type: 'primary_result',
      title: 'Primary result',
      claim_text: 'Draft claim',
      effective_claim_text: 'Draft claim',
      explanation: '',
      provenance: 'author_explicit',
      evidence_quality: 'direct',
      display_order: 0,
      node_signature: 'b'.repeat(64),
      evidence: [],
      issues: [],
      review: null
    }
  ],
  issues: [
    {
      id: 'issue-1',
      node_id: null,
      code: 'missing_core_node',
      severity: 'error',
      message: 'Missing limitations.'
    }
  ]
}

function job(status: ResearchMapJob['status'], stage: string = status): ResearchMapJob {
  return {
    id: 'job-1',
    document_id: 'doc-1',
    map_version_id: status === 'completed' ? 'map-1' : null,
    status,
    stage,
    progress: status === 'completed' || status === 'failed' ? 100 : 35,
    error_message: status === 'failed' ? 'Generation failed safely.' : null,
    attempt_count: 1,
    created_at: '2026-08-12T12:00:00Z',
    updated_at: '2026-08-12T12:00:01Z'
  }
}

describe('researchMapReducer', () => {
  it('loads a map, selects its first node, and exposes partial and stale warnings', () => {
    const loading = researchMapReducer(initialResearchMapState, { type: 'mapLoading' })
    const ready = researchMapReducer(loading, { type: 'mapLoaded', map })

    expect(loading.loadStatus).toBe('loading')
    expect(ready.loadStatus).toBe('ready')
    expect(ready.selectedNodeId).toBe('node-1')
    expect(ready.mapWarnings).toEqual({ partial: true, stale: true })
    expect(ready.mode).toBe('map')
  })

  it('models queued, running, completed, and failed job states without duplicate refreshes', () => {
    const queued = researchMapReducer(initialResearchMapState, {
      type: 'jobUpdated',
      job: job('queued')
    })
    const running = researchMapReducer(queued, {
      type: 'jobUpdated',
      job: job('running', 'validation')
    })
    const completed = researchMapReducer(running, {
      type: 'jobUpdated',
      job: job('completed')
    })
    const repeated = researchMapReducer(completed, {
      type: 'jobUpdated',
      job: job('completed')
    })
    const failed = researchMapReducer(initialResearchMapState, {
      type: 'jobUpdated',
      job: job('failed')
    })

    expect(queued.polling).toBe(true)
    expect(running.job?.stage).toBe('validation')
    expect(completed.polling).toBe(false)
    expect(completed.mapRefreshNonce).toBe(1)
    expect(repeated.mapRefreshNonce).toBe(1)
    expect(failed.polling).toBe(false)
    expect(failed.notice).toEqual({ kind: 'error', message: 'Generation failed safely.' })
  })

  it('bounds guided review and keeps inspector selection explicit', () => {
    let state = researchMapReducer(initialResearchMapState, { type: 'mapLoaded', map })
    state = researchMapReducer(state, { type: 'selectNode', nodeId: 'node-1' })
    state = researchMapReducer(state, { type: 'openInspector' })
    for (let index = 0; index < 8; index += 1) {
      state = researchMapReducer(state, { type: 'guidedNext' })
    }

    expect(state.inspectorOpen).toBe(true)
    expect(state.guidedStep).toBe(4)

    state = researchMapReducer(state, { type: 'guidedPrevious' })
    state = researchMapReducer(state, { type: 'closeInspector' })
    expect(state.guidedStep).toBe(3)
    expect(state.inspectorOpen).toBe(false)
  })

  it('rolls back an optimistic correction after a signature conflict', () => {
    let state = researchMapReducer(initialResearchMapState, { type: 'mapLoaded', map })
    state = researchMapReducer(state, {
      type: 'reviewOptimistic',
      requestId: 'request-1',
      nodeId: 'node-1',
      review
    })
    expect(state.map?.nodes[0].effective_claim_text).toBe('Corrected claim')
    expect(state.pendingReview?.nodeId).toBe('node-1')

    state = researchMapReducer(state, {
      type: 'reviewConflict',
      requestId: 'request-1',
      message: 'This claim changed. Reload the map and review it again.'
    })

    expect(state.map?.nodes[0].effective_claim_text).toBe('Draft claim')
    expect(state.map?.nodes[0].review).toBeNull()
    expect(state.pendingReview).toBeNull()
    expect(state.notice).toEqual({
      kind: 'error',
      message: 'This claim changed. Reload the map and review it again.'
    })
  })

  it('ignores a review response after its workspace request was replaced', () => {
    let state = researchMapReducer(initialResearchMapState, { type: 'mapLoaded', map })
    state = researchMapReducer(state, {
      type: 'reviewOptimistic',
      requestId: 'request-a',
      nodeId: 'node-1',
      review
    })
    state = researchMapReducer(state, { type: 'resetWorkspace' })
    state = researchMapReducer(state, { type: 'mapLoaded', map })

    state = researchMapReducer(state, {
      type: 'reviewSaved',
      requestId: 'request-a',
      nodeId: 'node-1',
      review: { ...review, id: 'late-server-review' }
    })

    expect(state.map?.nodes[0].review).toBeNull()
    expect(state.notice).toBeNull()
  })

  it('commits a server review and preserves map context through Reader mode', () => {
    let state = researchMapReducer(initialResearchMapState, { type: 'mapLoaded', map })
    state = researchMapReducer(state, { type: 'openInspector' })
    state = researchMapReducer(state, {
      type: 'reviewOptimistic',
      requestId: 'request-1',
      nodeId: 'node-1',
      review
    })
    state = researchMapReducer(state, {
      type: 'reviewSaved',
      requestId: 'request-1',
      nodeId: 'node-1',
      review: { ...review, id: 'server-review' }
    })
    state = researchMapReducer(state, { type: 'openReader', blockId: 'block-1' })

    expect(state.mode).toBe('reader')
    expect(state.readerFocusBlockId).toBe('block-1')
    expect(state.selectedNodeId).toBe('node-1')
    expect(state.inspectorOpen).toBe(true)

    state = researchMapReducer(state, { type: 'returnToMap' })
    expect(state.mode).toBe('map')
    expect(state.readerFocusBlockId).toBeNull()
    expect(state.map?.nodes[0].review?.id).toBe('server-review')
    expect(state.map?.reviewed_core_nodes).toBe(1)
  })
})

describe('pollResearchMapJob', () => {
  it('polls conditionally until terminal state and reports each job once', async () => {
    const jobs = [job('queued'), job('running', 'audit'), job('completed')]
    const fetchJob = vi.fn().mockImplementation(() => Promise.resolve(jobs.shift()!))
    const onJob = vi.fn()
    const waitForNextPoll = vi.fn().mockResolvedValue(undefined)

    const result = await pollResearchMapJob('job-1', {
      fetchJob,
      onJob,
      waitForNextPoll
    })

    expect(result?.status).toBe('completed')
    expect(fetchJob).toHaveBeenCalledTimes(3)
    expect(onJob).toHaveBeenCalledTimes(3)
    expect(waitForNextPoll).toHaveBeenCalledTimes(2)
  })

  it('stops before fetching when cancellation is already signaled', async () => {
    const controller = new AbortController()
    controller.abort()
    const fetchJob = vi.fn()

    const result = await pollResearchMapJob('job-1', {
      fetchJob,
      onJob: vi.fn(),
      signal: controller.signal,
      waitForNextPoll: vi.fn()
    })

    expect(result).toBeNull()
    expect(fetchJob).not.toHaveBeenCalled()
  })
})
