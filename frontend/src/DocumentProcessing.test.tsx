import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { DocumentProcessing, useDocumentProcessing } from './DocumentProcessing'
import { cancelProcessingJob, getProcessingPreflight, listProcessingJobs, processDocument } from './api'
import type { ProcessingJob } from './types'

vi.mock('./api', () => ({
  cancelProcessingJob: vi.fn(), getProcessingPreflight: vi.fn(),
  listProcessingJobs: vi.fn(), processDocument: vi.fn()
}))

const doc = { id: 'doc-1', title: 'paper.pdf', file_type: 'pdf', status: 'uploaded' as const }
const queued: ProcessingJob = {
  id: 'job-1', document_id: doc.id, status: 'queued', stage: 'queued',
  progress: 0, error_message: null
}
const onChanged = vi.fn().mockResolvedValue(undefined)
function Harness() {
  const processing = useDocumentProcessing(onChanged, 20)
  return <>
    {processing.loadError && <div role="alert">{processing.loadError}<button onClick={() => void processing.reload()}>Retry loading jobs</button></div>}
    <DocumentProcessing document={doc} processing={processing} />
  </>
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listProcessingJobs).mockResolvedValue([])
  vi.mocked(getProcessingPreflight).mockResolvedValue({
    ready: true, provider: 'orcarouter', source_type: 'text_pdf', page_count: 3, issues: []
  })
  vi.mocked(processDocument).mockResolvedValue(queued)
})

it('blocks submission and explains missing OCR before any processing request', async () => {
  vi.mocked(getProcessingPreflight).mockResolvedValue({
    ready: false, provider: 'orcarouter', source_type: 'image', page_count: 1,
    issues: [{ code: 'ocr_required', severity: 'error', message: 'Configure OCR for scanned documents.' }]
  })
  render(<Harness />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Process paper.pdf' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Process paper.pdf' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Configure OCR')
  expect(processDocument).not.toHaveBeenCalled()
})

it('shows queued work without claiming completion, then polls actual block progress', async () => {
  vi.mocked(listProcessingJobs).mockResolvedValueOnce([]).mockResolvedValue([{ ...queued, status: 'running', stage: 'translation', progress: 50, completed_blocks: 4, total_blocks: 10 }])
  render(<Harness />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Process paper.pdf' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Process paper.pdf' }))
  expect(await screen.findByRole('progressbar', { name: 'Processing paper.pdf' })).toBeInTheDocument()
  expect(screen.queryByText('Processed paper.pdf')).not.toBeInTheDocument()
  expect(await screen.findByText('4 / 10 blocks')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Process paper.pdf' })).toBeDisabled()
})

it('recovers running jobs on mount and refreshes documents once after completion', async () => {
  vi.mocked(listProcessingJobs).mockResolvedValueOnce([{ ...queued, status: 'running', stage: 'ocr', progress: 10 }])
    .mockResolvedValue([{ ...queued, status: 'completed', stage: 'completed', progress: 100 }])
  render(<Harness />)
  expect(await screen.findByRole('progressbar')).toBeInTheDocument()
  expect(await screen.findByText('Processed paper.pdf')).toBeInTheDocument()
  expect(onChanged).toHaveBeenCalledTimes(1)
  expect(processDocument).not.toHaveBeenCalled()
})

it('requests cooperative cancellation and explains the in-flight call boundary', async () => {
  let running: ProcessingJob = { ...queued, status: 'running', stage: 'translation', progress: 30 }
  vi.mocked(listProcessingJobs).mockImplementation(async () => [running])
  vi.mocked(cancelProcessingJob).mockImplementation(async () => {
    running = { ...running, cancel_requested: true }
    return running
  })
  render(<Harness />)
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel processing paper.pdf' }))
  expect(await screen.findByText(/current external call may finish/i)).toBeInTheDocument()
  expect(cancelProcessingJob).toHaveBeenCalledWith('job-1')
  expect(screen.getByRole('button', { name: 'Cancel processing paper.pdf' })).toBeDisabled()
})

it('allows retry of interrupted work through a fresh preflight', async () => {
  vi.mocked(listProcessingJobs).mockResolvedValue([{ ...queued, status: 'interrupted', stage: 'interrupted', error_message: 'Processing was interrupted. Retry with your current settings.' }])
  render(<Harness />)
  expect(await screen.findByText(/Processing was interrupted/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry processing paper.pdf' }))
  await waitFor(() => expect(processDocument).toHaveBeenCalledWith(doc.id))
  expect(getProcessingPreflight).toHaveBeenCalledWith(doc.id)
})

it('shows a safe processing failure without a success message', async () => {
  vi.mocked(processDocument).mockRejectedValue(new Error('This document is already being processed.'))
  render(<Harness />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Process paper.pdf' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Process paper.pdf' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already being processed')
  expect(screen.queryByText('Processed paper.pdf')).not.toBeInTheDocument()
})

it('makes job discovery failure visible and allows recovery', async () => {
  vi.mocked(listProcessingJobs).mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValue([])
  render(<Harness />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading jobs' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
})

it('does not start a job if unmounted while preflight is pending', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof getProcessingPreflight>>) => void
  vi.mocked(getProcessingPreflight).mockReturnValue(new Promise(done => { resolve = done }))
  const view = render(<Harness />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Process paper.pdf' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Process paper.pdf' }))
  view.unmount()
  resolve({ ready: true, provider: 'mock', source_type: 'text_pdf', page_count: 1, issues: [] })
  await Promise.resolve()
  expect(processDocument).not.toHaveBeenCalled()
})

it('ignores a stale polling response after cancellation', async () => {
  let resolveOld!: (jobs: ProcessingJob[]) => void
  vi.mocked(listProcessingJobs).mockResolvedValueOnce([])
  render(<Harness />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Process paper.pdf' })).toBeEnabled())
  vi.mocked(listProcessingJobs).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
  fireEvent.click(screen.getByRole('button', { name: 'Process paper.pdf' }))
  await screen.findByRole('progressbar')
  await waitFor(() => expect(resolveOld).toBeDefined())
  vi.mocked(cancelProcessingJob).mockResolvedValue({ ...queued, status: 'cancelled', stage: 'cancelled', error_message: null })
  fireEvent.click(screen.getByRole('button', { name: 'Cancel processing paper.pdf' }))
  await screen.findByText(/Processing cancelled/)
  await act(async () => { resolveOld([queued]) })
  await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument())
})
