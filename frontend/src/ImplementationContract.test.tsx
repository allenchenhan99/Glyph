import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ImplementationContract } from './ImplementationContract'
import { implementationContract } from './implementationContractTestData'
import {
  implementationContractDiff,
  implementationContractVersion
} from './implementationContractTestData'

const defaultProps = {
  contract: implementationContract,
  selectedItemId: 'item-portfolio',
  guidedStep: 0,
  inspectorOpen: true,
  notice: null,
  resolutionPending: false,
  onSelectItem: vi.fn(),
  onOpenInspector: vi.fn(),
  onCloseInspector: vi.fn(),
  onGuidedNext: vi.fn(),
  onGuidedPrevious: vi.fn(),
  onOpenReader: vi.fn(),
  onResolve: vi.fn(),
  onRemainBlocked: vi.fn()
}

describe('ImplementationContract', () => {
  it('renders the eight-section docket with counts, blockers, origins, and selected state', () => {
    render(<ImplementationContract {...defaultProps} />)

    const outline = screen.getByRole('navigation', { name: 'Implementation Contract outline' })
    expect(
      within(outline).getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)
    ).toEqual([
      '研究論點',
      '資料需求',
      '投資範圍與樣本',
      '訊號與時點',
      '投資組合建構',
      '評估',
      '交易摩擦與風險',
      '待決事項'
    ])
    expect(within(outline).getAllByText('1 item')).toHaveLength(8)
    expect(within(outline).getAllByText('1 blocker')).toHaveLength(2)
    expect(within(outline).getByText('人為決策')).toBeInTheDocument()
    expect(within(outline).getAllByText('缺失').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /weighting rule/i })).toHaveAttribute(
      'aria-current',
      'true'
    )
  })

  it('separates draft and effective values and makes readiness visible', () => {
    render(<ImplementationContract {...defaultProps} />)

    expect(screen.getByRole('status', { name: 'Contract readiness' })).toHaveTextContent(
      '尚未可實作2 blocking issues'
    )
    const comparison = screen.getByLabelText('Draft and effective value for weighting rule')
    expect(within(comparison).getByText('未提供')).toBeInTheDocument()
    expect(within(comparison).getByText('value_weight')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /ask|chat/i })).not.toBeInTheDocument()
  })

  it('shows partial and stale warnings without hiding the blocker state', () => {
    render(
      <ImplementationContract
        {...defaultProps}
        contract={{ ...implementationContract, is_current: false, is_stale: true }}
      />
    )

    expect(screen.getByText('Partial contract')).toBeInTheDocument()
    expect(screen.getByText(/source or Research Map changed/i)).toHaveAttribute('role', 'alert')
    expect(screen.getByRole('status', { name: 'Contract readiness' })).toHaveTextContent(
      '尚未可實作'
    )
  })

  it('makes a non-resolvable Contract visibly read-only and sends no decision', () => {
    const onResolve = vi.fn()
    render(
      <ImplementationContract
        {...defaultProps}
        contract={{ ...implementationContract, is_resolvable: false }}
        onResolve={onResolve}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent('read-only')
    expect(screen.getByRole('button', { name: 'Save human decision' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Keep item blocked' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save human decision' }))
    expect(onResolve).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Open Reader to investigate' })).toBeEnabled()
  })

  it('uses keyboard-reachable controls and supports controlled inspector collapse', () => {
    const onCloseInspector = vi.fn()
    const onOpenInspector = vi.fn()
    const first = render(
      <ImplementationContract {...defaultProps} onCloseInspector={onCloseInspector} />
    )

    const close = screen.getByRole('button', { name: 'Close Contract Inspector' })
    expect(close).not.toHaveAttribute('tabindex', '-1')
    fireEvent.click(close)
    expect(onCloseInspector).toHaveBeenCalledTimes(1)

    first.rerender(
      <ImplementationContract
        {...defaultProps}
        inspectorOpen={false}
        onOpenInspector={onOpenInspector}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Inspect selected contract item' }))
    expect(onOpenInspector).toHaveBeenCalledTimes(1)
  })

  it('switches deterministically between review, history, and export surfaces', () => {
    render(
      <ImplementationContract
        {...defaultProps}
        versions={[implementationContractVersion]}
        diff={implementationContractDiff}
        activationError={null}
        onSelectVersion={vi.fn()}
        onCompareVersions={vi.fn()}
        onActivateVersion={vi.fn()}
        onExport={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Open Contract history' }))
    expect(screen.getByLabelText('Contract version history')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open Contract export' }))
    expect(screen.getByLabelText('Contract export')).toHaveTextContent('NOT IMPLEMENTATION READY')
    fireEvent.click(screen.getByRole('button', { name: 'Return to Contract review' }))
    expect(screen.getByRole('navigation', { name: 'Implementation Contract outline' })).toBeInTheDocument()
  })
})
