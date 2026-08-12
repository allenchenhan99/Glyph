import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ResearchMap } from './ResearchMap'
import { researchMapFixture } from './researchMapTestData'

const defaultProps = {
  map: researchMapFixture,
  selectedNodeId: 'node-0',
  guidedStep: 0,
  inspectorOpen: true,
  notice: null,
  onSelectNode: vi.fn(),
  onOpenInspector: vi.fn(),
  onCloseInspector: vi.fn(),
  onGuidedNext: vi.fn(),
  onGuidedPrevious: vi.fn(),
  onOpenReader: vi.fn(),
  onReview: vi.fn(),
  onGenerate: vi.fn(),
  onBuildContract: vi.fn()
}

describe('ResearchMap', () => {
  it('renders six deterministic ontology categories with provenance and evidence quality', () => {
    render(<ResearchMap {...defaultProps} />)

    const outline = screen.getByRole('navigation', { name: 'Research Map outline' })
    expect(
      within(outline).getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
    ).toEqual([
      'Research question',
      'Data and sample',
      'Signal definition',
      'Empirical method',
      'Primary result',
      'Limitations'
    ])
    expect(screen.getAllByText('Author explicit').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Direct evidence').length).toBeGreaterThan(0)
    expect(screen.queryByRole('textbox', { name: /ask|chat/i })).not.toBeInTheDocument()
  })

  it('makes partial and stale trust states visible', () => {
    const onGenerate = vi.fn()
    render(<ResearchMap {...defaultProps} onGenerate={onGenerate} />)

    expect(screen.getByText('Partial map')).toBeInTheDocument()
    expect(screen.getByText('Source changed')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('missing implementation cost evidence')
    fireEvent.click(screen.getByRole('button', { name: 'Generate new version' }))
    expect(onGenerate).toHaveBeenCalledTimes(1)
  })

  it('shows an absent-map generation action and local-provider privacy notice', () => {
    const onGenerate = vi.fn()
    render(<ResearchMap {...defaultProps} map={null} onGenerate={onGenerate} />)

    fireEvent.click(screen.getByRole('button', { name: 'Generate Research Map' }))
    expect(onGenerate).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/processed by your configured local provider/i)).toBeInTheDocument()
  })

  it('shows persistent generation progress instead of a duplicate action', () => {
    render(
      <ResearchMap
        {...defaultProps}
        map={null}
        job={{
          id: 'job-1',
          document_id: 'doc-1',
          map_version_id: null,
          status: 'running',
          stage: 'validate evidence',
          progress: 64,
          error_message: null,
          attempt_count: 1,
          created_at: '2026-08-12T12:00:00Z',
          updated_at: '2026-08-12T12:00:01Z'
        }}
      />
    )

    expect(screen.getByRole('status')).toHaveTextContent('validate evidence64%')
    expect(screen.queryByRole('button', { name: 'Generate Research Map' })).not.toBeInTheDocument()
  })

  it('replaces stale regeneration with persistent job progress', () => {
    render(
      <ResearchMap
        {...defaultProps}
        job={{
          id: 'job-2',
          document_id: 'doc-1',
          map_version_id: null,
          status: 'running',
          stage: 'synthesize map',
          progress: 42,
          error_message: null,
          attempt_count: 1,
          created_at: '2026-08-12T12:00:00Z',
          updated_at: '2026-08-12T12:00:01Z'
        }}
      />
    )

    expect(screen.getByRole('status')).toHaveTextContent('synthesize map42%')
    expect(screen.queryByRole('button', { name: 'Generate new version' })).not.toBeInTheDocument()
  })

  it('builds a contract from the explicit active Map version', () => {
    const onBuildContract = vi.fn()
    const currentMap = { ...researchMapFixture, is_current: true, is_stale: false }
    render(
      <ResearchMap
        {...defaultProps}
        map={currentMap}
        onBuildContract={onBuildContract}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Build Implementation Contract' }))

    expect(onBuildContract).toHaveBeenCalledWith('map-1')
  })

  it('disables contract creation for a stale Map and explains recovery', () => {
    render(<ResearchMap {...defaultProps} />)

    expect(
      screen.getByRole('button', { name: 'Build Implementation Contract' })
    ).toBeDisabled()
    expect(screen.getByText(/refresh the source and Research Map/i)).toBeInTheDocument()
  })

  it('does not offer contract creation for an unfinished or failed Map', () => {
    render(
      <ResearchMap
        {...defaultProps}
        map={{
          ...researchMapFixture,
          status: 'failed',
          is_current: true,
          is_stale: false
        }}
      />
    )

    expect(
      screen.queryByRole('button', { name: 'Build Implementation Contract' })
    ).not.toBeInTheDocument()
  })
})
