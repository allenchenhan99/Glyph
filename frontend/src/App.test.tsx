import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import {
  ApiError,
  getDocumentSummaries,
  getProcessingPreflight,
  listProcessingJobs,
  getAiSettings,
  activateImplementationContract,
  enqueueImplementationContract,
  getActiveImplementationContract,
  getActiveResearchMap,
  getImplementationContractJob,
  getImplementationContractDiff,
  getImplementationContractExport,
  getImplementationContractVersion,
  getReader,
  getResearchMapVersion,
  listDocuments,
  listImplementationContractVersions,
  processDocument,
  resolveImplementationContractItem,
  reviewResearchNode,
  uploadDocument
} from './api'
import {
  implementationContract,
  implementationContractJob,
  implementationContractSummary,
  implementationContractVersion
} from './implementationContractTestData'
import { researchMapFixture } from './researchMapTestData'
import type { ImplementationContractVersion, ReaderPayload } from './types'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    getDocumentSummaries: vi.fn(),
    getProcessingPreflight: vi.fn(),
    listProcessingJobs: vi.fn(),
    getAiSettings: vi.fn(),
    listDocuments: vi.fn(),
    processDocument: vi.fn(),
    uploadDocument: vi.fn(),
    getReader: vi.fn(),
    getActiveResearchMap: vi.fn(),
    getResearchMapVersion: vi.fn(),
    enqueueImplementationContract: vi.fn(),
    getImplementationContractJob: vi.fn(),
    getActiveImplementationContract: vi.fn(),
    getImplementationContractVersion: vi.fn(),
    listImplementationContractVersions: vi.fn(),
    getImplementationContractDiff: vi.fn(),
    activateImplementationContract: vi.fn(),
    getImplementationContractExport: vi.fn(),
    resolveImplementationContractItem: vi.fn(),
    reviewResearchNode: vi.fn()
  }
})

const mockedListDocuments = vi.mocked(listDocuments)
const mockedGetReader = vi.mocked(getReader)
const mockedProcessDocument = vi.mocked(processDocument)
const mockedUploadDocument = vi.mocked(uploadDocument)
const mockedGetActiveResearchMap = vi.mocked(getActiveResearchMap)
const mockedGetResearchMapVersion = vi.mocked(getResearchMapVersion)
const mockedEnqueueImplementationContract = vi.mocked(enqueueImplementationContract)
const mockedGetImplementationContractJob = vi.mocked(getImplementationContractJob)
const mockedGetActiveImplementationContract = vi.mocked(getActiveImplementationContract)
const mockedGetImplementationContractVersion = vi.mocked(getImplementationContractVersion)
const mockedListImplementationContractVersions = vi.mocked(listImplementationContractVersions)
const mockedGetImplementationContractDiff = vi.mocked(getImplementationContractDiff)
const mockedActivateImplementationContract = vi.mocked(activateImplementationContract)
const mockedGetImplementationContractExport = vi.mocked(getImplementationContractExport)
const mockedResolveImplementationContractItem = vi.mocked(resolveImplementationContractItem)
const mockedReviewResearchNode = vi.mocked(reviewResearchNode)

const readerPayload: ReaderPayload = {
  document: {
    id: 'doc-1',
    title: 'sample.pdf',
    file_type: 'pdf',
    status: 'completed'
  },
  summary: 'Chapter One：共整理 1 個閱讀區塊。',
  sections: [
    {
      id: 'sec-1',
      title: 'Chapter One',
      path: 'Chapter One',
      order_index: 0,
      summary: 'Chapter One 的重點摘要。',
      progress: 100
    }
  ],
  blocks: [
    {
      id: 'block-0',
      order_index: 0,
      page_number: 1,
      block_type: 'heading',
      source_text: 'Chapter One',
      translated_text: '標題：Chapter One',
      formula_latex: null,
      page_image_url: '/api/documents/doc-1/pages/1/image',
      section_path: 'Chapter One',
      confidence: 1
    }
  ]
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getDocumentSummaries).mockResolvedValue({ status: 'not_generated', provider: 'mock', model: null, version: null, job: null })
    vi.mocked(listProcessingJobs).mockResolvedValue([])
    vi.mocked(getProcessingPreflight).mockResolvedValue({
      ready: true, provider: 'mock', source_type: 'text_pdf', page_count: 1, issues: []
    })
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed'
      }
    ])
    mockedGetReader.mockResolvedValue(readerPayload)
    mockedGetActiveResearchMap.mockResolvedValue(researchMapFixture)
    mockedGetResearchMapVersion.mockResolvedValue(researchMapFixture)
    mockedEnqueueImplementationContract.mockResolvedValue(implementationContractJob)
    mockedGetImplementationContractJob.mockResolvedValue({
      ...implementationContractJob,
      contract_version_id: implementationContract.id,
      status: 'completed',
      stage: 'completed',
      progress: 100
    })
    mockedGetActiveImplementationContract.mockResolvedValue(implementationContract)
    mockedGetImplementationContractVersion.mockResolvedValue(implementationContract)
    mockedListImplementationContractVersions.mockResolvedValue([])
    mockedGetImplementationContractDiff.mockResolvedValue({
      version_id: 'contract-1',
      against_version_id: 'contract-0',
      items: []
    })
    mockedActivateImplementationContract.mockResolvedValue(implementationContract)
    mockedGetImplementationContractExport.mockResolvedValue({
      blob: new Blob(['{}']),
      filename: 'implementation-contract-contract-1.en.json',
      content_type: 'application/json'
    })
    mockedProcessDocument.mockResolvedValue({
      id: 'job-1',
      document_id: 'doc-1',
      status: 'completed',
      stage: 'completed',
      progress: 100,
      error_message: null
    })
  })

  it('opens translation settings without losing the selected reader', async () => {
    vi.mocked(getAiSettings).mockResolvedValue({
      provider: 'claude_cli', model: '', has_api_key: false, ocr_mode: 'mock'
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Full Reader for sample.pdf' }))
    await screen.findByLabelText('Reader for sample.pdf')
    fireEvent.click(screen.getByRole('button', { name: 'Translation settings' }))
    expect(await screen.findByLabelText('Translation provider')).toHaveValue('claude_cli')
    expect(screen.getByLabelText('Reader for sample.pdf')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    expect(screen.queryByLabelText('Translation provider')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Reader for sample.pdf')).toBeInTheDocument()
  })

  it('opens the Research Map as the default research action when available', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))

    expect(await screen.findByLabelText('Research Map workspace')).toBeInTheDocument()
    expect(mockedGetActiveResearchMap).toHaveBeenCalledWith('doc-1')
    expect(mockedGetReader).not.toHaveBeenCalled()
  })

  it('offers generation when a completed Reader has no active Research Map', async () => {
    mockedGetActiveResearchMap.mockRejectedValue(new ApiError(404, 'Research Map not found'))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))

    expect(await screen.findByRole('button', { name: 'Generate Research Map' })).toBeInTheDocument()
    expect(screen.getByText(/configured local provider/i)).toBeInTheDocument()
  })

  it('rolls back a conflicting review and announces how to recover', async () => {
    mockedReviewResearchNode.mockRejectedValue(
      new ApiError(409, 'The claim changed after this map was loaded.')
    )
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm claim' }))

    const conflict = await screen.findByText(
      'The claim changed after this map was loaded. Reload the Research Map and review it again.'
    )
    expect(conflict).toHaveAttribute('role', 'alert')
    expect(screen.getAllByText('AI draft claim 0').length).toBeGreaterThan(0)
  })

  it('refreshes the authoritative Library summary after a saved review', async () => {
    mockedReviewResearchNode.mockResolvedValue({
      id: 'review-1',
      node_id: 'node-0',
      status: 'confirmed',
      corrected_claim_text: null,
      review_note: null,
      based_on_map_version_id: 'map-1',
      based_on_node_signature: '1'.repeat(64),
      revision_number: 1,
      supersedes_review_id: null,
      reviewed_at: '2026-08-12T12:01:00Z'
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm claim' }))

    expect(await screen.findByText('Review saved.')).toBeInTheDocument()
    await waitFor(() => expect(mockedListDocuments).toHaveBeenCalledTimes(2))
  })

  it('allows only one review request while a review is pending', async () => {
    let resolveReview!: (review: Awaited<ReturnType<typeof reviewResearchNode>>) => void
    mockedReviewResearchNode.mockReturnValue(
      new Promise((resolve) => {
        resolveReview = resolve
      })
    )
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    const confirm = await screen.findByRole('button', { name: 'Confirm claim' })

    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(mockedReviewResearchNode).toHaveBeenCalledTimes(1)
    expect(confirm).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Question claim' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save correction' })).toBeDisabled()

    resolveReview({
      id: 'review-1',
      node_id: 'node-0',
      status: 'confirmed',
      corrected_claim_text: null,
      review_note: null,
      based_on_map_version_id: 'map-1',
      based_on_node_signature: '1'.repeat(64),
      revision_number: 1,
      supersedes_review_id: null,
      reviewed_at: '2026-08-12T12:01:00Z'
    })
    expect(await screen.findByText('Review saved.')).toBeInTheDocument()
  })

  it('deep-links exact evidence into Reader and restores Map context on return', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'View evidence in Reader' }))

    const focused = await screen.findByTestId('reader-row-block-0')
    expect(focused).toHaveFocus()
    expect(focused).toHaveTextContent('Map citation · Research question')
    expect(mockedGetReader).toHaveBeenLastCalledWith('doc-1', researchMapFixture.source_content_hash)

    fireEvent.click(screen.getByRole('button', { name: 'Return to Research Map' }))
    expect(await screen.findByLabelText('Evidence Inspector for Research question')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Research question' })).toHaveAttribute(
      'aria-current',
      'true'
    )
  })

  it('detaches a previous document map when opening another document reader', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed'
      },
      {
        id: 'doc-2',
        title: 'second.pdf',
        file_type: 'pdf',
        status: 'completed'
      }
    ])
    mockedGetReader.mockImplementation(async (documentId) => ({
      ...readerPayload,
      document: {
        ...readerPayload.document,
        id: documentId,
        title: documentId === 'doc-2' ? 'second.pdf' : 'sample.pdf'
      },
      blocks: readerPayload.blocks.map((block) => ({
        ...block,
        id: documentId === 'doc-2' ? 'block-2' : block.id
      }))
    }))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    expect(await screen.findByLabelText('Research Map workspace')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open Full Reader for second.pdf' }))

    expect(await screen.findByLabelText('Reader for second.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Return to Research Map' })).not.toBeInTheDocument()
    expect(screen.queryByText('Map citation · Research question')).not.toBeInTheDocument()
  })

  it('shows verification, evidence gaps, and freshness in Library rows', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        research_map: {
          version_id: 'map-1',
          status: 'partial',
          is_current: true,
          is_stale: false,
          reviewed_core_nodes: 2,
          reviewable_core_nodes: 6,
          issue_count: 3
        }
      }
    ])
    render(<App />)

    expect(await screen.findByText('2 / 6 verified')).toBeInTheDocument()
    expect(screen.getByText('3 evidence gaps')).toBeInTheDocument()
    expect(screen.getByText('Current · partial')).toBeInTheDocument()
  })

  it('shows current contract readiness, blockers, freshness, and a resumable review in Library', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: {
          ...implementationContractSummary,
          is_current: true,
          is_stale: false
        }
      }
    ])
    render(<App />)

    expect(
      await screen.findByLabelText('Implementation Contract status for sample.pdf')
    ).toHaveTextContent('Blocked · 2 blockers')
    expect(screen.getByText('Current · partial')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Resume Contract for sample.pdf' }))
    expect(
      await screen.findByRole('navigation', { name: 'Implementation Contract outline' })
    ).toBeInTheDocument()
    expect(mockedGetActiveImplementationContract).toHaveBeenCalledWith('doc-1')
  })

  it('keeps Research Map primary when a current Map has no contract', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        research_map: {
          version_id: 'map-1',
          status: 'complete',
          is_current: true,
          is_stale: false,
          reviewed_core_nodes: 6,
          reviewable_core_nodes: 6,
          issue_count: 0
        }
      }
    ])
    render(<App />)

    expect(
      await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Resume Contract for sample.pdf' })
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open Research Map for sample.pdf' }))
    expect(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    ).toBeInTheDocument()
  })

  it('shows a stale contract without offering an unsafe resume action', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: {
          ...implementationContractSummary,
          is_current: false,
          is_stale: true
        }
      }
    ])
    render(<App />)

    expect(await screen.findByText('Stale · partial')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Resume Contract for sample.pdf' })
    ).not.toBeInTheDocument()
  })

  it('moves from Map to Contract to exact Reader evidence and refreshes Library', async () => {
    mockedGetActiveResearchMap.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
    })
    mockedGetReader.mockResolvedValue({
      ...readerPayload,
      blocks: [{ ...readerPayload.blocks[0], id: 'block-1' }]
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    )

    expect(
      await screen.findByRole('navigation', { name: 'Implementation Contract outline' })
    ).toBeInTheDocument()
    expect(mockedEnqueueImplementationContract).toHaveBeenCalledWith('doc-1', 'map-1')
    expect(mockedGetImplementationContractJob).toHaveBeenCalledWith('contract-job-1')
    expect(mockedGetActiveImplementationContract).toHaveBeenCalledWith('doc-1')
    await waitFor(() => expect(mockedListDocuments).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: 'Open evidence E01 in Reader' }))
    const focused = await screen.findByTestId('reader-row-block-1')
    await waitFor(() => expect(focused).toHaveFocus())
    expect(focused).toHaveTextContent('Contract citation · signal direction')
    expect(mockedGetReader).toHaveBeenCalledWith(
      'doc-1',
      implementationContract.source_content_hash
    )
  })

  it('opens exact Contract evidence in Reader and returns to the preserved Contract item', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedGetReader.mockResolvedValue({
      ...readerPayload,
      blocks: [{ ...readerPayload.blocks[0], id: 'block-1' }]
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open evidence E01 in Reader' }))

    const focused = await screen.findByTestId('reader-row-block-1')
    await waitFor(() => expect(focused).toHaveFocus())
    expect(mockedGetReader).toHaveBeenCalledWith(
      'doc-1',
      implementationContract.source_content_hash
    )
    fireEvent.click(screen.getByRole('button', { name: 'Return to Implementation Contract' }))
    expect(
      await screen.findByLabelText('Contract Inspector for Signal direction')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Signal direction' })).toHaveAttribute(
      'aria-current',
      'true'
    )
  })

  it('rolls back an optimistic Contract decision after a signature conflict', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedResolveImplementationContractItem.mockRejectedValue(
      new ApiError(409, 'The contract item changed after this review opened.')
    )
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Universe filter' }))
    fireEvent.change(screen.getByLabelText('Decision value'), {
      target: { value: 'NYSE common shares' }
    })
    fireEvent.change(screen.getByLabelText('Decision reason'), {
      target: { value: 'Matches the desk mandate.' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save human decision' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The contract item changed after this review opened. Reload the Implementation Contract and decide again.'
    )
    expect(mockedResolveImplementationContractItem).toHaveBeenCalledWith(
      'item-universe',
      expect.objectContaining({
        status: 'decided',
        based_on_item_signature: 'b'.repeat(64),
        resolved_value: { kind: 'scalar', value: 'NYSE common shares' },
        reason: 'Matches the desk mandate.'
      })
    )
    expect(screen.getByRole('group', { name: 'Resolve missing implementation value' })).toBeInTheDocument()
  })

  it('refreshes the open Contract audit after a saved resolution', async () => {
    const initialContract = {
      ...implementationContract,
      readiness: 'review_needed' as const,
      issues: []
    }
    const questionedResolution = {
      id: 'resolution-questioned',
      item_id: 'item-thesis',
      revision_number: 1,
      supersedes_resolution_id: null,
      status: 'questioned' as const,
      resolved_value: null,
      reason: null,
      based_on_contract_version_id: implementationContract.id,
      based_on_item_signature: 'b'.repeat(64),
      request_id: 'contract-resolution-1',
      resolved_at: '2026-08-13T00:00:00Z'
    }
    const refreshedContract = {
      ...initialContract,
      readiness: 'blocked' as const,
      items: initialContract.items.map((item) =>
        item.id === 'item-thesis'
          ? {
              ...item,
              resolution: questionedResolution,
              resolution_history: [questionedResolution]
            }
          : item
      ),
      issues: [
        {
          id: 'issue-questioned',
          item_id: 'item-thesis',
          code: 'questioned_item',
          severity: 'error' as const,
          message: 'A reviewed implementation value is still questioned.'
        }
      ]
    }
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: {
          ...implementationContractSummary,
          readiness: 'review_needed',
          blocker_count: 0
        }
      }
    ])
    mockedGetActiveImplementationContract
      .mockResolvedValueOnce(initialContract)
      .mockResolvedValueOnce(refreshedContract)
    mockedResolveImplementationContractItem.mockResolvedValue(questionedResolution)

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    expect(await screen.findByRole('status', { name: 'Contract readiness' })).toHaveTextContent(
      '需要人工審查0 blocking issues'
    )

    fireEvent.click(screen.getByRole('button', { name: 'Question supported item' }))

    await waitFor(() =>
      expect(screen.getByRole('status', { name: 'Contract readiness' })).toHaveTextContent(
        '尚未可實作1 blocking issue'
      )
    )
    expect(mockedGetActiveImplementationContract).toHaveBeenCalledTimes(2)
  })

  it('never keeps a ready label when the authoritative post-save audit cannot load', async () => {
    const readyContract = {
      ...implementationContract,
      readiness: 'implementation_ready' as const,
      issues: []
    }
    const questionedResolution = {
      id: 'resolution-questioned',
      item_id: 'item-thesis',
      revision_number: 2,
      supersedes_resolution_id: 'resolution-confirmed',
      status: 'questioned' as const,
      resolved_value: null,
      reason: 'Needs another review.',
      based_on_contract_version_id: implementationContract.id,
      based_on_item_signature: 'b'.repeat(64),
      request_id: 'contract-resolution-1',
      resolved_at: '2026-08-13T00:00:00Z'
    }
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: {
          ...implementationContractSummary,
          readiness: 'implementation_ready',
          blocker_count: 0
        }
      }
    ])
    mockedGetActiveImplementationContract
      .mockResolvedValueOnce(readyContract)
      .mockRejectedValueOnce(new ApiError(503, 'Audit reload unavailable.'))
      .mockResolvedValueOnce({ ...readyContract, readiness: 'blocked' })
    mockedResolveImplementationContractItem.mockResolvedValue(questionedResolution)

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    expect(await screen.findByText('可進入實作')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Question supported item' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Readiness could not be verified after saving the decision.'
    )
    expect(screen.queryByText('可進入實作')).not.toBeInTheDocument()
    expect(
      screen.getByLabelText('Implementation Contract status for sample.pdf')
    ).toHaveTextContent('Readiness unverified')
    expect(
      screen.getByLabelText('Implementation Contract status for sample.pdf')
    ).not.toHaveTextContent('Implementation ready')
    fireEvent.click(screen.getByRole('button', { name: 'Reload Implementation Contract' }))
    expect(await screen.findByText('尚未可實作')).toBeInTheDocument()
  })

  it('uses the authoritative open Contract when the post-save Library refresh fails', async () => {
    const readyContract = {
      ...implementationContract,
      readiness: 'implementation_ready' as const,
      issues: []
    }
    const questionedResolution = {
      id: 'resolution-questioned',
      item_id: 'item-thesis',
      revision_number: 2,
      supersedes_resolution_id: 'resolution-confirmed',
      status: 'questioned' as const,
      resolved_value: null,
      reason: 'Needs another review.',
      based_on_contract_version_id: implementationContract.id,
      based_on_item_signature: 'b'.repeat(64),
      request_id: 'contract-resolution-1',
      resolved_at: '2026-08-13T00:00:00Z'
    }
    const blockedContract = {
      ...readyContract,
      readiness: 'blocked' as const,
      items: readyContract.items.map((item) =>
        item.id === 'item-thesis'
          ? { ...item, resolution: questionedResolution }
          : item
      ),
      issues: [
        {
          id: 'issue-questioned',
          item_id: 'item-thesis',
          code: 'questioned_item',
          severity: 'error' as const,
          message: 'A reviewed implementation value is still questioned.'
        }
      ]
    }
    const readyDocument = {
      id: 'doc-1',
      title: 'sample.pdf',
      file_type: 'pdf',
      status: 'completed' as const,
      implementation_contract: {
        ...implementationContractSummary,
        readiness: 'implementation_ready' as const,
        blocker_count: 0
      }
    }
    mockedListDocuments
      .mockResolvedValueOnce([readyDocument])
      .mockRejectedValueOnce(new ApiError(503, 'Library refresh unavailable.'))
    mockedGetActiveImplementationContract
      .mockResolvedValueOnce(readyContract)
      .mockResolvedValueOnce(blockedContract)
    mockedResolveImplementationContractItem.mockResolvedValue(questionedResolution)

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Question supported item' }))

    expect(await screen.findByText('尚未可實作')).toBeInTheDocument()
    const library = screen.getByLabelText('Implementation Contract status for sample.pdf')
    expect(library).toHaveTextContent('Blocked · 1 blocker')
    expect(library).not.toHaveTextContent('Implementation ready')
  })

  it('opens a linked Research Map node from Contract and returns to the same Contract item', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedGetResearchMapVersion.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Required dataset' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open linked Research Map node' }))

    expect(await screen.findByLabelText('Evidence Inspector for Data and sample')).toBeInTheDocument()
    expect(mockedGetResearchMapVersion).toHaveBeenCalledWith(
      implementationContract.research_map_version_id
    )
    fireEvent.click(screen.getByRole('button', { name: 'Return to Implementation Contract' }))
    expect(await screen.findByRole('button', { name: 'Required dataset' })).toHaveAttribute(
      'aria-current',
      'true'
    )
  })

  it('ignores late Contract Reader and Map deep links from a previous document', async () => {
    let resolveReader!: (payload: ReaderPayload) => void
    let resolveMap!: (map: typeof researchMapFixture) => void
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      },
      {
        id: 'doc-2',
        title: 'second.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedGetActiveImplementationContract.mockImplementation(async (documentId) => ({
      ...implementationContract,
      id: documentId === 'doc-2' ? 'contract-2' : implementationContract.id,
      document_id: documentId
    }))
    mockedGetReader.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveReader = resolve
      })
    )
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open evidence E01 in Reader' }))
    fireEvent.click(screen.getByRole('button', { name: 'Resume Contract for second.pdf' }))
    await screen.findByRole('navigation', { name: 'Implementation Contract outline' })
    await act(async () => {
      resolveReader({ ...readerPayload, blocks: [{ ...readerPayload.blocks[0], id: 'block-1' }] })
      await Promise.resolve()
    })
    expect(screen.queryByTestId('reader-row-block-1')).not.toBeInTheDocument()

    mockedGetResearchMapVersion.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveMap = resolve
      })
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Required dataset' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open linked Research Map node' }))
    fireEvent.click(screen.getByRole('button', { name: 'Resume Contract for sample.pdf' }))
    await screen.findByRole('navigation', { name: 'Implementation Contract outline' })
    await act(async () => {
      resolveMap(researchMapFixture)
      await Promise.resolve()
    })
    expect(screen.queryByLabelText('Evidence Inspector for Data and sample')).not.toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Implementation Contract outline' })).toBeInTheDocument()
  })

  it('loads Contract history and surfaces an activation conflict without false freshness', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedListImplementationContractVersions.mockResolvedValue([
      {
        id: implementationContract.id,
        document_id: implementationContract.document_id,
        research_map_version_id: implementationContract.research_map_version_id,
        previous_version_id: implementationContract.previous_version_id,
        source_content_hash: implementationContract.source_content_hash,
        research_map_signature: implementationContract.research_map_signature,
        schema_version: implementationContract.schema_version,
        provider: implementationContract.provider,
        model_name: implementationContract.model_name,
        status: implementationContract.status,
        readiness: implementationContract.readiness,
        is_active: true,
        is_current: true,
        is_stale: false,
        created_at: implementationContract.created_at,
        completed_at: implementationContract.completed_at
      },
      {
        ...implementationContractVersion,
        id: 'contract-0',
        is_active: false,
        is_current: false,
        is_stale: true
      }
    ])
    mockedActivateImplementationContract.mockRejectedValue(
      new ApiError(409, 'The version changed before activation.')
    )
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open Contract history' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Activate contract-0' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm activation of contract-0' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The version changed before activation.')
    expect(screen.getByLabelText('Contract version contract-0')).toHaveTextContent('Stale')
    expect(screen.getByLabelText('Contract version contract-0')).not.toHaveTextContent('Current')
  })

  it('clears Contract selections and history when switching documents', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      },
      {
        id: 'doc-2',
        title: 'second.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedListImplementationContractVersions.mockResolvedValue([
      implementationContractVersion
    ])
    mockedGetActiveImplementationContract.mockImplementation(async (documentId) => ({
      ...implementationContract,
      id: documentId === 'doc-2' ? 'contract-2' : implementationContract.id,
      document_id: documentId
    }))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Required dataset' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open Contract history' }))
    expect(await screen.findByLabelText('Contract version history')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Resume Contract for second.pdf' }))
    expect(
      await screen.findByRole('navigation', { name: 'Implementation Contract outline' })
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Contract version history')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Signal direction' })).toHaveAttribute(
      'aria-current',
      'true'
    )
  })

  it('ignores late Contract history and activation results from a previous document', async () => {
    let resolveHistory!: (versions: ImplementationContractVersion[]) => void
    let rejectActivation!: (reason: unknown) => void
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      },
      {
        id: 'doc-2',
        title: 'second.pdf',
        file_type: 'pdf',
        status: 'completed',
        implementation_contract: implementationContractSummary
      }
    ])
    mockedGetActiveImplementationContract.mockImplementation(async (documentId) => ({
      ...implementationContract,
      id: documentId === 'doc-2' ? 'contract-2' : implementationContract.id,
      document_id: documentId
    }))
    mockedListImplementationContractVersions.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveHistory = resolve
      })
    )
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Resume Contract for sample.pdf' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open Contract history' }))
    fireEvent.click(screen.getByRole('button', { name: 'Resume Contract for second.pdf' }))
    await screen.findByRole('navigation', { name: 'Implementation Contract outline' })
    mockedListImplementationContractVersions.mockReturnValueOnce(new Promise(() => {}))
    fireEvent.click(screen.getByRole('button', { name: 'Open Contract history' }))
    await act(async () => {
      resolveHistory([{ ...implementationContractVersion, id: 'old-doc-version' }])
      await Promise.resolve()
    })
    expect(screen.queryByText('old-doc-version')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Return to Contract review' }))

    mockedListImplementationContractVersions.mockResolvedValue([
      {
        ...implementationContractVersion,
        id: 'contract-0',
        document_id: 'doc-2',
        is_active: false,
        is_current: false,
        is_stale: true
      }
    ])
    mockedActivateImplementationContract.mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectActivation = reject
      })
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Open Contract history' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Activate contract-0' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm activation of contract-0' }))
    fireEvent.click(screen.getByRole('button', { name: 'Resume Contract for sample.pdf' }))
    rejectActivation(new ApiError(409, 'Old document activation conflict.'))
    await waitFor(() => {
      expect(screen.queryByText('Old document activation conflict.')).not.toBeInTheDocument()
    })
  })

  it('keeps contract polling progress visible', async () => {
    mockedGetActiveResearchMap.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
    })
    mockedGetImplementationContractJob.mockResolvedValue({
      ...implementationContractJob,
      status: 'running',
      stage: 'extract contract rules',
      progress: 45
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    )

    expect(await screen.findByRole('status')).toHaveTextContent('extract contract rules45%')
  })

  it('surfaces failed and duplicate contract jobs without claiming readiness', async () => {
    mockedGetActiveResearchMap.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
    })
    mockedGetImplementationContractJob.mockResolvedValue({
      ...implementationContractJob,
      status: 'failed',
      stage: 'failed',
      progress: 100,
      error_message: 'Contract generation failed safely.'
    })
    const first = render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Contract generation failed safely.')
    expect(screen.queryByText('Contract ready for review')).not.toBeInTheDocument()

    first.unmount()
    vi.clearAllMocks()
    mockedListDocuments.mockResolvedValue([
      { id: 'doc-1', title: 'sample.pdf', file_type: 'pdf', status: 'completed' }
    ])
    mockedGetActiveResearchMap.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
    })
    mockedEnqueueImplementationContract.mockRejectedValue(
      new ApiError(409, 'An Implementation Contract job is already active.')
    )
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'An Implementation Contract job is already active.'
    )
  })

  it('aborts contract polling on document switch and unmount', async () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
    mockedListDocuments.mockResolvedValue([
      { id: 'doc-1', title: 'sample.pdf', file_type: 'pdf', status: 'completed' },
      { id: 'doc-2', title: 'second.pdf', file_type: 'pdf', status: 'completed' }
    ])
    mockedGetActiveResearchMap.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
    })
    mockedGetImplementationContractJob.mockReturnValue(new Promise(() => undefined))
    const view = render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    )
    await waitFor(() => expect(mockedGetImplementationContractJob).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'Open Full Reader for second.pdf' }))
    await waitFor(() => expect(abortSpy).toHaveBeenCalledTimes(1))
    view.unmount()

    const unmountView = render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Research Map for sample.pdf' }))
    fireEvent.click(
      await screen.findByRole('button', { name: 'Build Implementation Contract' })
    )
    await waitFor(() => expect(mockedGetImplementationContractJob).toHaveBeenCalledTimes(2))
    unmountView.unmount()
    expect(abortSpy).toHaveBeenCalledTimes(2)
    abortSpy.mockRestore()
  })

  it('shows discovered documents from the book folder', async () => {
    render(<App />)

    expect(await screen.findByText('sample.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Process sample.pdf' })).toBeInTheDocument()
  })

  it('keeps the document picker compact after opening the reader', async () => {
    render(<App />)

    const library = await screen.findByRole('region', { name: 'Reading workspace' })
    fireEvent.click(await screen.findByRole('button', { name: 'Open Full Reader for sample.pdf' }))

    expect(await screen.findByLabelText('Reader for sample.pdf')).toBeInTheDocument()
    expect(library).toHaveClass('library-panel-compact')
  })

  it('explains when a source changed and needs reprocessing', async () => {
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'stale'
      }
    ])

    render(<App />)

    expect(await screen.findByText('PDF · Source changed — reprocess required')).toBeInTheDocument()
  })

  it('shows a processing conflict without claiming success', async () => {
    mockedProcessDocument.mockRejectedValue(
      new ApiError(409, 'This document is already being processed.')
    )

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Process sample.pdf' }))

    expect(await screen.findByText('This document is already being processed.')).toBeInTheDocument()
    expect(screen.queryByText('Processed sample.pdf')).not.toBeInTheDocument()
  })

  it('treats a failed processing job as an error even when the request succeeded', async () => {
    mockedProcessDocument.mockResolvedValue({
      id: 'job-1',
      document_id: 'doc-1',
      status: 'failed',
      stage: 'failed',
      progress: 100,
      error_message: 'Unlimited-OCR is selected but not configured.'
    })

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Process sample.pdf' }))

    expect(
      await screen.findByText('Unlimited-OCR is selected but not configured.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Processed sample.pdf')).not.toBeInTheDocument()
  })

  it('shows a safe upload error returned by the backend', async () => {
    mockedUploadDocument.mockRejectedValue(new ApiError(413, 'Upload exceeds the 50 MiB limit.'))

    render(<App />)
    const file = new File(['%PDF-1.4'], 'large.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('Upload document'), { target: { files: [file] } })

    expect(await screen.findByText('Upload exceeds the 50 MiB limit.')).toBeInTheDocument()
  })
})


it('does not claim an uploaded source is ready before preflight', async () => {
  mockedListDocuments.mockResolvedValue([{ id: 'doc-1', title: 'scan.png', file_type: 'png', status: 'uploaded' }])
  vi.mocked(listProcessingJobs).mockResolvedValue([])
  render(<App />)
  expect(await screen.findByText('PNG · Uploaded · not processed')).toBeInTheDocument()
})
