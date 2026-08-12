import { describe, expect, it, vi } from 'vitest'

import {
  implementationContractReducer,
  initialImplementationContractState,
  pollImplementationContractJob
} from './implementationContractState'
import {
  contractResolution,
  implementationContract,
  implementationContractJob
} from './implementationContractTestData'
import type {
  ContractResolution,
  ImplementationContractJob,
  ImplementationContractJobStatus
} from './types'

const decision: ContractResolution = {
  ...contractResolution,
  id: 'optimistic-decision',
  item_id: 'item-universe',
  status: 'decided',
  resolved_value: { kind: 'scalar', value: 'NYSE common stocks' },
  reason: 'Match the exchange and share-code filters stated by the paper.',
  based_on_item_signature: 'b'.repeat(64),
  request_id: 'request-1'
}

const job = (
  status: ImplementationContractJobStatus,
  stage: string = status
): ImplementationContractJob => ({
  ...implementationContractJob,
  contract_version_id: status === 'completed' ? 'contract-1' : null,
  status,
  stage,
  progress: status === 'completed' || status === 'failed' ? 100 : 45,
  error_message: status === 'failed' ? 'Generation failed safely.' : null,
  attempt_count: status === 'queued' ? 0 : 1
})

describe('implementationContractReducer', () => {
  it('models idle, loading, absent, ready, and error for the active document', () => {
    const loading = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    const absent = implementationContractReducer(loading, {
      type: 'contractAbsent',
      documentId: 'doc-1'
    })
    const ready = implementationContractReducer(absent, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: implementationContract
    })
    const failed = implementationContractReducer(ready, {
      type: 'contractFailed',
      documentId: 'doc-1',
      message: 'Could not load contract.'
    })

    expect(initialImplementationContractState.loadStatus).toBe('idle')
    expect(loading.loadStatus).toBe('loading')
    expect(absent.loadStatus).toBe('absent')
    expect(ready.loadStatus).toBe('ready')
    expect(ready.selectedItemId).toBe('item-thesis')
    expect(failed.loadStatus).toBe('error')
    expect(failed.notice).toEqual({ kind: 'error', message: 'Could not load contract.' })
  })

  it('ignores a late load or failure from a previous document', () => {
    const first = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    const second = implementationContractReducer(first, {
      type: 'resetDocument',
      documentId: 'doc-2'
    })

    expect(
      implementationContractReducer(second, {
        type: 'contractLoaded',
        documentId: 'doc-1',
        contract: implementationContract
      })
    ).toEqual(second)
    expect(
      implementationContractReducer(second, {
        type: 'contractFailed',
        documentId: 'doc-1',
        message: 'Late failure.'
      })
    ).toEqual(second)
  })

  it('selects items, exposes stale and blocker warnings, and bounds six guided steps', () => {
    let state = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    state = implementationContractReducer(state, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: { ...implementationContract, is_current: false, is_stale: true }
    })
    state = implementationContractReducer(state, {
      type: 'selectItem',
      itemId: 'item-universe'
    })
    state = implementationContractReducer(state, { type: 'openInspector' })
    for (let index = 0; index < 8; index += 1) {
      state = implementationContractReducer(state, { type: 'guidedNext' })
    }

    expect(state.selectedItemId).toBe('item-universe')
    expect(state.inspectorOpen).toBe(true)
    expect(state.guidedStep).toBe(5)
    expect(state.contractWarnings).toEqual({
      stale: true,
      blocked: true,
      blockerCount: 2
    })

    for (let index = 0; index < 8; index += 1) {
      state = implementationContractReducer(state, { type: 'guidedPrevious' })
    }
    state = implementationContractReducer(state, { type: 'closeInspector' })
    expect(state.guidedStep).toBe(0)
    expect(state.inspectorOpen).toBe(false)
  })

  it('models queued, running, completed, and failed generation without duplicate refreshes', () => {
    const queued = implementationContractReducer(initialImplementationContractState, {
      type: 'jobUpdated',
      documentId: 'doc-1',
      job: job('queued')
    })
    const running = implementationContractReducer(queued, {
      type: 'jobUpdated',
      documentId: 'doc-1',
      job: job('running', 'validate_evidence')
    })
    const completed = implementationContractReducer(running, {
      type: 'jobUpdated',
      documentId: 'doc-1',
      job: job('completed')
    })
    const repeated = implementationContractReducer(completed, {
      type: 'jobUpdated',
      documentId: 'doc-1',
      job: job('completed')
    })
    const failed = implementationContractReducer(initialImplementationContractState, {
      type: 'jobUpdated',
      documentId: 'doc-1',
      job: job('failed')
    })

    expect(queued.polling).toBe(true)
    expect(running.job?.stage).toBe('validate_evidence')
    expect(completed.polling).toBe(false)
    expect(completed.contractRefreshNonce).toBe(1)
    expect(repeated.contractRefreshNonce).toBe(1)
    expect(failed.notice).toEqual({ kind: 'error', message: 'Generation failed safely.' })
  })

  it('applies and commits an optimistic human decision', () => {
    let state = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    state = implementationContractReducer(state, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: implementationContract
    })
    state = implementationContractReducer(state, {
      type: 'selectItem',
      itemId: 'item-universe'
    })
    state = implementationContractReducer(state, {
      type: 'resolutionOptimistic',
      requestId: 'request-1',
      itemId: 'item-universe',
      resolution: decision
    })

    const optimistic = state.contract?.items.find((item) => item.id === 'item-universe')
    expect(optimistic?.effective_origin).toBe('human_decision')
    expect(optimistic?.effective_value).toEqual(decision.resolved_value)
    expect(state.pendingResolution?.requestId).toBe('request-1')

    state = implementationContractReducer(state, {
      type: 'resolutionSaved',
      requestId: 'request-1',
      itemId: 'item-universe',
      resolution: { ...decision, id: 'server-decision' }
    })
    const saved = state.contract?.items.find((item) => item.id === 'item-universe')
    expect(saved?.resolution?.id).toBe('server-decision')
    expect(saved?.resolution_history.at(-1)?.id).toBe('server-decision')
    expect(state.pendingResolution).toBeNull()
    expect(state.notice).toEqual({ kind: 'status', message: 'Decision saved.' })
  })

  it('locks out reason-required decisions before optimistic mutation', () => {
    let state = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    state = implementationContractReducer(state, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: implementationContract
    })
    const unchanged = state.contract

    state = implementationContractReducer(state, {
      type: 'resolutionOptimistic',
      requestId: 'request-invalid',
      itemId: 'item-universe',
      resolution: { ...decision, request_id: 'request-invalid', reason: null }
    })

    expect(state.contract).toEqual(unchanged)
    expect(state.pendingResolution).toBeNull()
    expect(state.notice).toEqual({
      kind: 'error',
      message: 'A decided resolution requires a value and reason.'
    })
  })

  it('rolls back an optimistic decision after a conflict', () => {
    let state = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    state = implementationContractReducer(state, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: implementationContract
    })
    state = implementationContractReducer(state, {
      type: 'resolutionOptimistic',
      requestId: 'request-1',
      itemId: 'item-universe',
      resolution: decision
    })
    state = implementationContractReducer(state, {
      type: 'resolutionConflict',
      requestId: 'request-1',
      message: 'The item changed. Reload and decide again.'
    })

    const restored = state.contract?.items.find((item) => item.id === 'item-universe')
    expect(restored?.effective_origin).toBe('missing')
    expect(restored?.effective_value).toBeNull()
    expect(restored?.resolution).toBeNull()
    expect(state.pendingResolution).toBeNull()
  })

  it('ignores a late resolution from a previous item or obsolete request', () => {
    let state = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    state = implementationContractReducer(state, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: implementationContract
    })
    state = implementationContractReducer(state, {
      type: 'resolutionOptimistic',
      requestId: 'request-1',
      itemId: 'item-universe',
      resolution: decision
    })
    state = implementationContractReducer(state, {
      type: 'selectItem',
      itemId: 'item-signal'
    })
    const switched = state

    expect(
      implementationContractReducer(switched, {
        type: 'resolutionSaved',
        requestId: 'request-0',
        itemId: 'item-universe',
        resolution: decision
      })
    ).toEqual(switched)
    expect(
      implementationContractReducer(switched, {
        type: 'resolutionSaved',
        requestId: 'request-1',
        itemId: 'item-universe',
        resolution: decision
      })
    ).toEqual(switched)
  })

  it('records Contract as the Reader return surface', () => {
    let state = implementationContractReducer(initialImplementationContractState, {
      type: 'contractLoading',
      documentId: 'doc-1'
    })
    state = implementationContractReducer(state, {
      type: 'contractLoaded',
      documentId: 'doc-1',
      contract: implementationContract
    })
    state = implementationContractReducer(state, {
      type: 'openReader',
      blockId: 'block-2'
    })

    expect(state.readerFocusBlockId).toBe('block-2')
    expect(state.returnSurface).toBe('contract')
    expect(state.selectedItemId).toBe('item-thesis')

    state = implementationContractReducer(state, { type: 'returnToContract' })
    expect(state.readerFocusBlockId).toBeNull()
    expect(state.returnSurface).toBeNull()
  })
})

describe('pollImplementationContractJob', () => {
  it('polls until terminal state and reports each durable stage', async () => {
    const jobs = [
      job('queued'),
      job('running', 'synthesize_contract'),
      job('completed')
    ]
    const fetchJob = vi.fn().mockImplementation(() => Promise.resolve(jobs.shift()!))
    const onJob = vi.fn()
    const waitForNextPoll = vi.fn().mockResolvedValue(undefined)

    const result = await pollImplementationContractJob('contract-job-1', {
      fetchJob,
      onJob,
      waitForNextPoll
    })

    expect(result?.status).toBe('completed')
    expect(fetchJob).toHaveBeenCalledTimes(3)
    expect(onJob).toHaveBeenCalledTimes(3)
    expect(waitForNextPoll).toHaveBeenCalledTimes(2)
  })

  it('aborts without delivering a late job response', async () => {
    const controller = new AbortController()
    let release: ((value: ReturnType<typeof job>) => void) | undefined
    const fetchJob = vi.fn().mockImplementation(
      () =>
        new Promise<ReturnType<typeof job>>((resolve) => {
          release = resolve
        })
    )
    const onJob = vi.fn()
    const polling = pollImplementationContractJob('contract-job-1', {
      fetchJob,
      onJob,
      signal: controller.signal,
      waitForNextPoll: vi.fn()
    })

    controller.abort()
    release?.(job('completed'))

    await expect(polling).resolves.toBeNull()
    expect(onJob).not.toHaveBeenCalled()
  })
})
