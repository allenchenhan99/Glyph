import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EvidenceInspector } from './EvidenceInspector'
import { researchMapFixture } from './researchMapTestData'

describe('EvidenceInspector', () => {
  it('shows exact bilingual evidence, locator, relation, and Reader action', () => {
    const onOpenReader = vi.fn()
    render(
      <EvidenceInspector
        node={researchMapFixture.nodes[4]}
        onClose={vi.fn()}
        onOpenReader={onOpenReader}
        onReview={vi.fn()}
      />
    )

    expect(screen.getByText('Verbatim source evidence 4')).toBeInTheDocument()
    expect(screen.getByText('繁體中文證據翻譯 4')).toBeInTheDocument()
    expect(screen.getByText(/Page 5/)).toBeInTheDocument()
    expect(screen.getByText(/Table · Supports/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View evidence in Reader' }))
    expect(onOpenReader).toHaveBeenCalledWith('block-4')
  })

  it('offers confirm, question, and correction while requiring corrected text', () => {
    const onReview = vi.fn()
    render(
      <EvidenceInspector
        node={researchMapFixture.nodes[0]}
        onClose={vi.fn()}
        onOpenReader={vi.fn()}
        onReview={onReview}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Confirm claim' }))
    fireEvent.click(screen.getByRole('button', { name: 'Question claim' }))
    expect(onReview).toHaveBeenNthCalledWith(1, 'confirmed', null, null)
    expect(onReview).toHaveBeenNthCalledWith(2, 'questioned', null, null)

    const correctButton = screen.getByRole('button', { name: 'Save correction' })
    expect(correctButton).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Corrected claim' }), {
      target: { value: 'A narrower corrected claim.' }
    })
    fireEvent.click(correctButton)
    expect(onReview).toHaveBeenLastCalledWith('corrected', 'A narrower corrected claim.', null)
  })

  it('keeps the immutable AI draft available after a human correction', () => {
    const corrected = {
      ...researchMapFixture.nodes[0],
      effective_claim_text: 'Human corrected claim',
      review: {
        id: 'review-1',
        status: 'corrected' as const,
        corrected_claim_text: 'Human corrected claim',
        review_note: 'Scope correction',
        revision_number: 1,
        supersedes_review_id: null,
        reviewed_at: '2026-08-12T12:00:00Z'
      }
    }
    render(
      <EvidenceInspector
        node={corrected}
        onClose={vi.fn()}
        onOpenReader={vi.fn()}
        onReview={vi.fn()}
      />
    )

    expect(screen.getAllByText('Human corrected claim').length).toBeGreaterThan(0)
    expect(screen.getByText('Original AI draft')).toBeInTheDocument()
    expect(screen.getByText('AI draft claim 0')).toBeInTheDocument()
  })
})
