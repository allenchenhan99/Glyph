import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { getReader, listDocuments } from './api'
import type { ReaderPayload } from './types'

vi.mock('./api', () => ({
  listDocuments: vi.fn(),
  processDocument: vi.fn(),
  uploadDocument: vi.fn(),
  getReader: vi.fn()
}))

const mockedListDocuments = vi.mocked(listDocuments)
const mockedGetReader = vi.mocked(getReader)

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
    mockedListDocuments.mockResolvedValue([
      {
        id: 'doc-1',
        title: 'sample.pdf',
        file_type: 'pdf',
        status: 'completed'
      }
    ])
    mockedGetReader.mockResolvedValue(readerPayload)
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
})
