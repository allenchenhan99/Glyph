import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { ApiError, getReader, listDocuments, processDocument, uploadDocument } from './api'
import type { ReaderPayload } from './types'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    listDocuments: vi.fn(),
    processDocument: vi.fn(),
    uploadDocument: vi.fn(),
    getReader: vi.fn()
  }
})

const mockedListDocuments = vi.mocked(listDocuments)
const mockedGetReader = vi.mocked(getReader)
const mockedProcessDocument = vi.mocked(processDocument)
const mockedUploadDocument = vi.mocked(uploadDocument)

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
      id: 'block-1',
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
    mockedProcessDocument.mockResolvedValue({
      id: 'job-1',
      document_id: 'doc-1',
      status: 'completed',
      stage: 'completed',
      progress: 100,
      error_message: null
    })
  })

  it('shows discovered documents from the book folder', async () => {
    render(<App />)

    expect(await screen.findByText('sample.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Process sample.pdf' })).toBeInTheDocument()
  })

  it('keeps the document picker compact after opening the reader', async () => {
    render(<App />)

    const library = await screen.findByRole('region', { name: 'Reading workspace' })
    fireEvent.click(await screen.findByRole('button', { name: 'Open sample.pdf' }))

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
