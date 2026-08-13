import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ContractVersions } from './ContractVersions'
import {
  implementationContractDiff,
  implementationContractVersion
} from './implementationContractTestData'

const staleVersion = {
  ...implementationContractVersion,
  id: 'contract-0',
  is_active: false,
  is_current: false,
  is_stale: true,
  created_at: '2026-08-11T12:00:00Z'
}

const defaultProps = {
  versions: [implementationContractVersion, staleVersion],
  selectedVersionId: 'contract-1',
  diff: implementationContractDiff,
  activationError: null,
  onSelectVersion: vi.fn(),
  onCompare: vi.fn(),
  onActivate: vi.fn()
}

describe('ContractVersions', () => {
  it('labels current, stale, and active states independently', () => {
    render(<ContractVersions {...defaultProps} />)

    const current = screen.getByLabelText('Contract version contract-1')
    expect(current).toHaveTextContent('Active')
    expect(current).toHaveTextContent('Current')
    const stale = screen.getByLabelText('Contract version contract-0')
    expect(stale).toHaveTextContent('Stale')
    expect(stale).not.toHaveTextContent('Current')
  })

  it('groups backend diff classifications deterministically', () => {
    render(
      <ContractVersions
        {...defaultProps}
        diff={{
          version_id: 'contract-1',
          against_version_id: 'contract-0',
          items: [
            ...implementationContractDiff.items,
            {
              item_key: 'required_dataset.1',
              classification: 'evidence_changed',
              version_item_id: 'item-data',
              against_item_id: 'item-data-old'
            },
            {
              item_key: 'weighting_rule.1',
              classification: 'origin_changed',
              version_item_id: 'item-portfolio',
              against_item_id: 'item-portfolio-old'
            }
          ]
        }}
      />
    )

    const groups = screen.getByLabelText('Contract version differences')
    expect(within(groups).getAllByRole('heading', { level: 4 }).map((node) => node.textContent)).toEqual([
      'Value changed',
      'Origin changed',
      'Evidence changed'
    ])
  })

  it('requires activation confirmation and surfaces a 409 without claiming current', () => {
    const onActivate = vi.fn()
    const view = render(
      <ContractVersions {...defaultProps} onActivate={onActivate} />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Activate contract-0' }))
    expect(screen.getByText(/activating this history version does not make stale inputs current/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm activation of contract-0' }))
    expect(onActivate).toHaveBeenCalledWith('contract-0')

    view.rerender(
      <ContractVersions
        {...defaultProps}
        versions={[{ ...staleVersion, is_active: true }]}
        selectedVersionId="contract-0"
        activationError="This version changed while activation was pending."
      />
    )
    expect(screen.getByRole('alert')).toHaveTextContent(
      'This version changed while activation was pending.'
    )
    const staleActive = screen.getByLabelText('Contract version contract-0')
    expect(staleActive).toHaveTextContent('Active')
    expect(staleActive).toHaveTextContent('Stale')
    expect(staleActive).not.toHaveTextContent('Current')
  })
})
