import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import {
  ApiError,
  getActiveResearchMap,
  getReader,
  listDocuments,
  processDocument,
  reviewResearchNode,
  uploadDocument
} from './api'
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
    reviewResearchNode: vi.fn()
  }
})

const mockedListDocuments = vi.mocked(listDocuments)
const mockedGetReader = vi.mocked(getReader)
const mockedProcessDocument = vi.mocked(processDocument)
const mockedUploadDocument = vi.mocked(uploadDocument)
const mockedGetActiveResearchMap = vi.mocked(getActiveResearchMap)
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
