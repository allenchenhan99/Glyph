import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import { SummaryPanel } from './SummaryPanel'
import type { DocumentSummaries, SummaryVersion } from './types'

vi.mock('./api', () => ({ getDocumentSummaries: vi.fn(), generateDocumentSummaries: vi.fn() }))

const empty: DocumentSummaries = { status: 'not_generated', provider: 'claude_cli', model: null, version: null, job: null }
const version: SummaryVersion = {
  id: 'v1', source_content_hash: 'a'.repeat(64), reader_fingerprint: 'b'.repeat(64),
  provider: 'claude_cli', model: null, created_at: '2026-09-13T12:00:00Z',
  claims: [{ id: 'c1', section_path: null, text: 'Returns remain uncertain.', evidence: [
    { block_id: 'b1', quote_text: 'Expected return is uncertain.', quote_start: 0, quote_end: 29, page_number: 1 }
  ] }]
}
const available: DocumentSummaries = { ...empty, status: 'available', version }
const generating: DocumentSummaries = { ...empty, status: 'generating', job: { id: 'j1', status: 'running', error_message: null } }
const read = vi.mocked(api.getDocumentSummaries)
const generate = vi.mocked(api.generateDocumentSummaries)
const props = { documentId: 'd1', blockIds: ['b1'], onNavigate: vi.fn(), pollInterval: 10 }

describe('SummaryPanel', () => {
  beforeEach(() => { vi.resetAllMocks(); read.mockResolvedValue(empty) })

  it('requires explicit generation and explains the selected provider', async () => {
    generate.mockResolvedValue(generating)
    render(<SummaryPanel {...props} />)
    expect(await screen.findByText('No summary generated yet.')).toBeInTheDocument()
    expect(screen.getByText(/claude_cli/)).toBeInTheDocument()
    expect(generate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Generate summary' }))
    await waitFor(() => expect(generate).toHaveBeenCalledWith('d1'))
  })

  it('restores a running job and polls until its evidence is available', async () => {
    read.mockResolvedValueOnce(generating).mockResolvedValue(available)
    render(<SummaryPanel {...props} />)
    expect(await screen.findByText(/Generating summary/)).toBeInTheDocument()
    expect(await screen.findByText('Returns remain uncertain.')).toBeInTheDocument()
    expect(generate).not.toHaveBeenCalled()
  })

  it('shows AI draft status and exact quotes with source navigation', async () => {
    read.mockResolvedValue(available)
    render(<SummaryPanel {...props} />)
    expect(await screen.findByText(/AI draft/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Returns remain uncertain.'))
    expect(screen.getByText('Expected return is uncertain.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Go to source page 1' }))
    expect(props.onNavigate).toHaveBeenCalledWith('b1')
  })

  it('retains the last summary when generation fails and offers retry', async () => {
    read.mockResolvedValue({ ...available, status: 'failed', job: { id: 'j2', status: 'failed', error_message: 'Provider unavailable.' } })
    render(<SummaryPanel {...props} />)
    expect(await screen.findByText('Provider unavailable.')).toBeInTheDocument()
    expect(screen.getByText('Returns remain uncertain.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry summary' })).toBeInTheDocument()
    expect(screen.getByText(/Previous summary retained/)).toBeInTheDocument()
  })

  it('keeps stale quotes visible without linking to absent Reader blocks', async () => {
    read.mockResolvedValue({ ...available, status: 'stale' })
    render(<SummaryPanel {...props} blockIds={['replacement']} />)
    expect(await screen.findByText(/different Reader version/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Returns remain uncertain.'))
    expect(screen.getByText('Expected return is uncertain.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Go to source page 1' })).not.toBeInTheDocument()
  })

  it('labels deterministic development output separately', async () => {
    read.mockResolvedValue({ ...available, provider: 'mock', version: { ...version, provider: 'mock' } })
    render(<SummaryPanel {...props} />)
    expect(await screen.findByText(/Development output/)).toBeInTheDocument()
  })

  it('does not generate current summaries from a historical evidence view', async () => {
    render(<SummaryPanel {...props} canGenerate={false} />)
    expect(await screen.findByText(/Open Full Reader/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate summary' })).not.toBeInTheDocument()
    expect(generate).not.toHaveBeenCalled()
  })

  it('offers reload after a discovery error', async () => {
    read.mockRejectedValueOnce(new Error('Cannot load summaries.')).mockResolvedValue(empty)
    render(<SummaryPanel {...props} />)
    expect(await screen.findByText('Cannot load summaries.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reload summaries' }))
    expect(await screen.findByText('No summary generated yet.')).toBeInTheDocument()
  })

  it('does not replace a new document with a late generation response', async () => {
    let resolve!: (value: DocumentSummaries) => void
    generate.mockReturnValue(new Promise((done) => { resolve = done }))
    const view = render(<SummaryPanel {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Generate summary' }))
    view.rerender(<SummaryPanel {...props} documentId="d2" />)
    await screen.findByText('No summary generated yet.')
    await act(async () => resolve(available))
    expect(screen.queryByText('Returns remain uncertain.')).not.toBeInTheDocument()
  })
})
