import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ContractInspector } from './ContractInspector'
import { implementationContract } from './implementationContractTestData'

const item = (id: string) => implementationContract.items.find((value) => value.id === id)!

const defaultProps = {
  pending: false,
  notice: null,
  onClose: vi.fn(),
  onOpenReader: vi.fn(),
  onResolve: vi.fn(),
  onRemainBlocked: vi.fn()
}

describe('ContractInspector', () => {
  it('shows direct anchors for author-explicit items and opens the exact Reader block', () => {
    const onOpenReader = vi.fn()
    render(
      <ContractInspector
        {...defaultProps}
        item={item('item-thesis')}
        onOpenReader={onOpenReader}
      />
    )

    expect(screen.getByText('作者明示')).toBeInTheDocument()
    expect(screen.getByText('The signal uses lagged book-to-market.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open evidence E01 in Reader' }))
    expect(onOpenReader).toHaveBeenCalledWith('block-1')
  })

  it('can confirm, question, or correct supported items', () => {
    const onResolve = vi.fn()
    render(
      <ContractInspector
        {...defaultProps}
        item={item('item-thesis')}
        onResolve={onResolve}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Confirm supported item' }))
    expect(onResolve).toHaveBeenLastCalledWith('confirmed', null, null)
    fireEvent.change(screen.getByLabelText('Review reason'), {
      target: { value: 'The source remains ambiguous.' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Question supported item' }))
    expect(onResolve).toHaveBeenLastCalledWith(
      'questioned',
      null,
      'The source remains ambiguous.'
    )
    fireEvent.change(screen.getByLabelText('Corrected value'), {
      target: { value: 'low_minus_high' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save supported-item correction' }))
    expect(onResolve).toHaveBeenLastCalledWith(
      'corrected',
      { kind: 'scalar', value: 'low_minus_high' },
      'The source remains ambiguous.'
    )
  })

  it('names decision fields for browser form semantics', () => {
    const view = render(<ContractInspector {...defaultProps} item={item('item-thesis')} />)

    expect(screen.getByLabelText('Corrected value')).toHaveAttribute(
      'name',
      'contract-item-item-thesis-value'
    )
    expect(screen.getByLabelText('Review reason')).toHaveAttribute(
      'name',
      'contract-item-item-thesis-reason'
    )

    view.rerender(<ContractInspector {...defaultProps} item={item('item-open')} />)
    expect(screen.getByLabelText('Decision value')).toHaveAttribute(
      'name',
      'contract-item-item-open-value'
    )
    expect(screen.getByLabelText('Decision reason')).toHaveAttribute(
      'name',
      'contract-item-item-open-reason'
    )
  })

  it('shows at least two anchors and rationale for derived items', () => {
    render(<ContractInspector {...defaultProps} item={item('item-data')} />)

    expect(screen.getByText('推導')).toBeInTheDocument()
    expect(screen.getAllByRole('blockquote')).toHaveLength(2)
    expect(
      screen.getByText('Two source anchors jointly identify the required datasets.')
    ).toBeInTheDocument()
  })

  it('shows the reason and revision history for human decisions', () => {
    render(<ContractInspector {...defaultProps} item={item('item-portfolio')} />)

    expect(screen.getByText('人為決策')).toBeInTheDocument()
    expect(
      screen.getAllByText('Use the paper’s reported value-weighted construction.').length
    ).toBeGreaterThan(0)
    expect(screen.getByText('Revision 1 · decided')).toBeInTheDocument()
  })

  it('offers only valid missing-value choices and never auto-fills a default', () => {
    render(<ContractInspector {...defaultProps} item={item('item-universe')} />)

    expect(screen.getByRole('button', { name: 'Keep item blocked' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save human decision' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark item not applicable' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Reader to investigate' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /default|auto-fill/i })).not.toBeInTheDocument()
  })

  it('offers not-applicable only for optional items and a structured gross decision for costs', () => {
    const onResolve = vi.fn()
    const view = render(
      <ContractInspector {...defaultProps} item={item('item-open')} onResolve={onResolve} />
    )
    expect(screen.getByRole('button', { name: 'Mark item not applicable' })).toBeInTheDocument()

    view.rerender(
      <ContractInspector {...defaultProps} item={item('item-friction')} onResolve={onResolve} />
    )
    expect(screen.queryByRole('button', { name: 'Mark item not applicable' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Decision reason'), {
      target: { value: 'Reproduce the paper’s reported gross returns.' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Record gross replication' }))
    expect(onResolve).toHaveBeenCalledWith(
      'decided',
      { kind: 'scalar', value: 'gross_replication' },
      'Reproduce the paper’s reported gross returns.'
    )
  })

  it('associates validation and server conflicts with the decision form', () => {
    const onResolve = vi.fn()
    const view = render(
      <ContractInspector
        {...defaultProps}
        item={item('item-open')}
        onResolve={onResolve}
      />
    )

    fireEvent.change(screen.getByLabelText('Decision value'), {
      target: { value: 'NYSE common shares' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save human decision' }))
    const validation = screen.getByRole('alert')
    expect(validation).toHaveTextContent('Explain why this decision is appropriate.')
    expect(screen.getByLabelText('Decision reason')).toHaveAttribute('aria-describedby', validation.id)
    expect(onResolve).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Decision reason'), {
      target: { value: 'Matches the investable universe used by the desk.' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save human decision' }))
    expect(onResolve).toHaveBeenCalledWith(
      'decided',
      { kind: 'scalar', value: 'NYSE common shares' },
      'Matches the investable universe used by the desk.'
    )

    view.rerender(
      <ContractInspector
        {...defaultProps}
        item={item('item-open')}
        notice={{ kind: 'error', message: 'This item changed. Reload the contract.' }}
      />
    )
    const conflict = screen.getByText('This item changed. Reload the contract.')
    expect(conflict).toHaveAttribute('role', 'alert')
    expect(screen.getByRole('group', { name: 'Resolve missing implementation value' })).toHaveAttribute(
      'aria-describedby',
      conflict.id
    )
  })

  it('requires a reason for not-applicable and locks controls while pending', () => {
    const onResolve = vi.fn()
    const view = render(
      <ContractInspector
        {...defaultProps}
        item={item('item-open')}
        onResolve={onResolve}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Mark item not applicable' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Explain why this item is not applicable.'
    )

    view.rerender(
      <ContractInspector {...defaultProps} item={item('item-open')} pending />
    )
    expect(screen.getByLabelText('Decision value')).toBeDisabled()
    expect(screen.getByLabelText('Decision reason')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save human decision' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Mark item not applicable' })).toBeDisabled()
  })
})
