import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GettingStarted } from './GettingStarted'
import type { WorkspaceStatus } from './types'
import { implementationContractSummary } from './implementationContractTestData'

const workspace: WorkspaceStatus = {
  status: 'ready', development_features: ['translation', 'summaries', 'research_maps', 'implementation_contracts'], recovery: null,
  translation: { provider: 'mock', configured: true, message: 'Development translation.' },
  research: { provider: 'mock', configured: true, message: 'Development research output.' },
  ocr: { provider: 'mock', configured: true, message: 'Text PDFs only; scanned pages need OCR.' }
}
const actions = { onSettings: vi.fn(), onUpload: vi.fn(), onRead: vi.fn(), onMap: vi.fn(), onContract: vi.fn() }

describe('GettingStarted', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const values = new Map<string, string>()
    vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value) })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('guides an empty workspace without making provider requests', () => {
    render(<GettingStarted workspace={workspace} documents={[]} {...actions} />)
    expect(screen.getByText('Start with one document')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Choose translation provider' }))
    fireEvent.click(screen.getByRole('button', { name: 'Upload your first document' }))
    expect(actions.onSettings).toHaveBeenCalledOnce()
    expect(actions.onUpload).toHaveBeenCalledOnce()
    expect(screen.getByText(/Deterministic development output/)).toBeInTheDocument()
  })

  it('keeps development labels visible when the guide is hidden and can reopen it', () => {
    const view = render(<GettingStarted workspace={workspace} documents={[]} {...actions} />)
    fireEvent.click(screen.getByRole('button', { name: 'Hide getting started' }))
    expect(screen.queryByText('Start with one document')).not.toBeInTheDocument()
    expect(screen.getByText(/Deterministic development output/)).toBeInTheDocument()
    view.unmount()
    render(<GettingStarted workspace={workspace} documents={[]} {...actions} />)
    expect(screen.queryByText('Start with one document')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show getting started' }))
    expect(screen.getByText('Start with one document')).toBeInTheDocument()
  })

  it('lets returning users resume a readable document and existing contract', () => {
    const document = { id: 'd1', title: 'paper.pdf', file_type: 'pdf', status: 'completed' as const,
      implementation_contract: implementationContractSummary }
    render(<GettingStarted workspace={workspace} documents={[document]} {...actions} />)
    expect(screen.queryByText('Start with one document')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue reading paper.pdf' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue research for paper.pdf' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue contract for paper.pdf' }))
    expect(actions.onRead).toHaveBeenCalledWith(document)
    expect(actions.onMap).toHaveBeenCalledWith(document)
    expect(actions.onContract).toHaveBeenCalledWith(document)
  })

  it('shows independent provider setup needs without calling them authenticated', () => {
    render(<GettingStarted workspace={{ ...workspace, development_features: [],
      translation: { provider: 'orcarouter', configured: true, message: 'Configuration present; credentials are not verified.' },
      research: { provider: 'claude_cli', configured: false, message: 'Install the Claude CLI for summaries and research.' }
    }} documents={[]} {...actions} />)
    expect(screen.getByText(/Translation: orcarouter/)).toBeInTheDocument()
    expect(screen.getByText(/Research: claude_cli/)).toBeInTheDocument()
    expect(screen.getByText('Install the Claude CLI for summaries and research.')).toBeInTheDocument()
    expect(screen.queryByText(/Deterministic development output/)).not.toBeInTheDocument()
  })

  it('remains usable when browser storage is unavailable', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('Storage blocked') }, setItem: () => { throw new Error('Storage blocked') } })
    render(<GettingStarted workspace={workspace} documents={[]} {...actions} />)
    fireEvent.click(screen.getByRole('button', { name: 'Hide getting started' }))
    fireEvent.click(screen.getByRole('button', { name: 'Show getting started' }))
    expect(screen.getByText('Start with one document')).toBeInTheDocument()
  })
})
