import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ContractExport } from './ContractExport'

describe('ContractExport', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:contract-export'),
      revokeObjectURL: vi.fn()
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('selects format and language and exposes the backend filename', async () => {
    const onExport = vi.fn().mockResolvedValue({
      blob: new Blob(['contract']),
      filename: 'implementation-contract-contract-1.zh-TW.md',
      content_type: 'text/markdown'
    })
    render(
      <ContractExport readiness="blocked" blockerCount={2} onExport={onExport} />
    )

    fireEvent.change(screen.getByLabelText('Export format'), { target: { value: 'markdown' } })
    fireEvent.change(screen.getByLabelText('Export language'), { target: { value: 'zh-TW' } })
    fireEvent.click(screen.getByRole('button', { name: 'Download contract export' }))

    await waitFor(() => expect(onExport).toHaveBeenCalledWith('markdown', 'zh-TW'))
    expect(
      await screen.findByRole('link', {
        name: 'Download implementation-contract-contract-1.zh-TW.md again'
      })
    ).toHaveAttribute('download', 'implementation-contract-contract-1.zh-TW.md')
  })

  it('warns explicitly without optimistically claiming readiness', () => {
    render(
      <ContractExport readiness="blocked" blockerCount={2} onExport={vi.fn()} />
    )

    expect(screen.getByRole('alert')).toHaveTextContent('NOT IMPLEMENTATION READY')
    expect(screen.getByRole('alert')).toHaveTextContent('2 blockers')
    expect(screen.queryByText('Implementation ready')).not.toBeInTheDocument()
  })

  it('recovers from an API error and keeps the profitability boundary visible for ready exports', async () => {
    const onExport = vi
      .fn()
      .mockRejectedValueOnce(new Error('Export unavailable.'))
      .mockResolvedValueOnce({
        blob: new Blob(['{}']),
        filename: 'implementation-contract-contract-1.en.json',
        content_type: 'application/json'
      })
    render(
      <ContractExport
        readiness="implementation_ready"
        blockerCount={0}
        onExport={onExport}
      />
    )

    expect(screen.getByText(/Glyph does not validate profitability/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Download contract export' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Export unavailable.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry contract export' }))
    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('link')).toHaveAttribute(
      'download',
      'implementation-contract-contract-1.en.json'
    )
  })
})
