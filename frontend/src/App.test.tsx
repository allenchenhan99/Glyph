import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import {
  ApiError,
  enqueueImplementationContract,
  getActiveImplementationContract,
  getActiveResearchMap,
  getImplementationContractJob,
  getReader,
  listDocuments,
  processDocument,
  resolveImplementationContractItem,
  reviewResearchNode,
  uploadDocument
} from './api'
import {
  implementationContract,
  implementationContractJob,
  implementationContractSummary
} from './implementationContractTestData'
import { researchMapFixture } from './researchMapTestData'
import type { ReaderPayload } from './types'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    listDocuments: vi.fn(),
    processDocument: vi.fn(),
    uploadDocument: vi.fn(),
    getReader: vi.fn(),
    getActiveResearchMap: vi.fn(),
    enqueueImplementationContract: vi.fn(),
    getImplementationContractJob: vi.fn(),
    getActiveImplementationContract: vi.fn(),
    resolveImplementationContractItem: vi.fn(),
    reviewResearchNode: vi.fn()
  }
})

const mockedListDocuments = vi.mocked(listDocuments)
const mockedGetReader = vi.mocked(getReader)
const mockedProcessDocument = vi.mocked(processDocument)
const mockedUploadDocument = vi.mocked(uploadDocument)
const mockedGetActiveResearchMap = vi.mocked(getActiveResearchMap)
const mockedEnqueueImplementationContract = vi.mocked(enqueueImplementationContract)
const mockedGetImplementationContractJob = vi.mocked(getImplementationContractJob)
const mockedGetActiveImplementationContract = vi.mocked(getActiveImplementationContract)
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
    mockedEnqueueImplementationContract.mockResolvedValue(implementationContractJob)
    mockedGetImplementationContractJob.mockResolvedValue({
      ...implementationContractJob,
      contract_version_id: implementationContract.id,
      status: 'completed',
      stage: 'completed',
      progress: 100
    })
    mockedGetActiveImplementationContract.mockResolvedValue(implementationContract)
    mockedProcessDocument.mockResolvedValue({
      id: 'job-1',
      document_id: 'doc-1',
      status: 'completed',
      stage: 'completed',
      progress: 100,
      error_message: null
    })
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
    expect(focused).toHaveTextContent('Cited by Research question')

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
    expect(screen.queryByText('Cited by Research question')).not.toBeInTheDocument()
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

  it('enqueues from the explicit Map version, loads completion, and refreshes Library', async () => {
    mockedGetActiveResearchMap.mockResolvedValue({
      ...researchMapFixture,
      is_current: true,
      is_stale: false
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

    expect(await screen.findByTestId('reader-row-block-1')).toHaveFocus()
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
