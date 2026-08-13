import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ContractGuidedReview } from './ContractGuidedReview'
import { implementationContract } from './implementationContractTestData'

describe('ContractGuidedReview', () => {
  it('renders exactly six deterministic Traditional Chinese review steps', () => {
    render(
      <ContractGuidedReview
        contract={implementationContract}
        step={0}
        onPrevious={vi.fn()}
        onNext={vi.fn()}
        onInspectItem={vi.fn()}
      />
    )

    const progress = screen.getByRole('list', { name: 'Implementation review progress' })
    expect(within(progress).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      '1資料可得性',
      '2樣本與投資範圍',
      '3訊號與時間規則',
      '4投資組合建構',
      '5評估與交易摩擦',
      '6解決阻擋項目並匯出'
    ])
  })

  it('shows only the mapped sections and the strongest exact evidence for a step', () => {
    const onInspectItem = vi.fn()
    render(
      <ContractGuidedReview
        contract={implementationContract}
        step={0}
        onPrevious={vi.fn()}
        onNext={vi.fn()}
        onInspectItem={onInspectItem}
      />
    )

    expect(screen.getByRole('heading', { name: '資料可得性' })).toBeInTheDocument()
    expect(screen.getByText('Required dataset')).toBeInTheDocument()
    expect(screen.queryByText('Signal formula')).not.toBeInTheDocument()
    expect(screen.getByText('Accounting data become available after six months.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /inspect required dataset/i }))
    expect(onInspectItem).toHaveBeenCalledWith('item-data')
  })

  it('surfaces the strongest blocker and keeps next/previous boundaries deterministic', () => {
    const onPrevious = vi.fn()
    const onNext = vi.fn()
    const view = render(
      <ContractGuidedReview
        contract={implementationContract}
        step={1}
        onPrevious={onPrevious}
        onNext={onNext}
        onInspectItem={vi.fn()}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      'A blocking implementation value remains missing.'
    )
    fireEvent.click(screen.getByRole('button', { name: 'Previous contract review step' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next contract review step' }))
    expect(onPrevious).toHaveBeenCalledTimes(1)
    expect(onNext).toHaveBeenCalledTimes(1)

    view.rerender(
      <ContractGuidedReview
        contract={implementationContract}
        step={5}
        onPrevious={onPrevious}
        onNext={onNext}
        onInspectItem={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: 'Next contract review step' })).toBeDisabled()
  })
})
