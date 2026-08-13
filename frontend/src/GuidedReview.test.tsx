import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { GuidedReview } from './GuidedReview'
import { researchMapFixture } from './researchMapTestData'

describe('GuidedReview', () => {
  it('renders a bounded five-step path and the strongest exact evidence', () => {
    const onNext = vi.fn()
    const onPrevious = vi.fn()
    const { rerender } = render(
      <GuidedReview
        map={researchMapFixture}
        step={0}
        onInspectEvidence={vi.fn()}
        onNext={onNext}
        onPrevious={onPrevious}
      />
    )

    expect(screen.getByText('Step 1 of 5')).toBeInTheDocument()
    expect(screen.getByText('AI draft claim 0')).toBeInTheDocument()
    expect(screen.getByText('Verbatim source evidence 0')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous review step' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next review step' }))
    expect(onNext).toHaveBeenCalledTimes(1)

    rerender(
      <GuidedReview
        map={researchMapFixture}
        step={4}
        onInspectEvidence={vi.fn()}
        onNext={onNext}
        onPrevious={onPrevious}
      />
    )
    expect(screen.getByText('Step 5 of 5')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next review step' })).toBeDisabled()
  })

  it('shows a structured issue instead of silently skipping a missing stage', () => {
    const mapWithoutSignal = {
      ...researchMapFixture,
      nodes: researchMapFixture.nodes.filter((node) => node.node_type !== 'signal_definition'),
      issues: [
        {
          id: 'missing-signal',
          node_id: null,
          code: 'missing_core_node',
          severity: 'error' as const,
          message: 'The Research Map is missing its signal category.'
        }
      ]
    }
    render(
      <GuidedReview
        map={mapWithoutSignal}
        step={2}
        onInspectEvidence={vi.fn()}
        onNext={vi.fn()}
        onPrevious={vi.fn()}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent('missing its signal category')
  })
})
