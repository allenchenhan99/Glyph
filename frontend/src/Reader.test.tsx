import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Reader } from './Reader'
import type { ReaderPayload } from './types'

const payload: ReaderPayload = {
  document: {
    id: 'doc-1',
    title: 'sample.pdf',
    file_type: 'pdf',
    status: 'completed'
  },
  summary: 'Introduction：共整理 2 個閱讀區塊。',
  sections: [
    {
      id: 'sec-1',
      title: 'Introduction',
      path: 'Introduction',
      order_index: 0,
      summary: 'Introduction 的重點摘要。',
      progress: 100
    }
  ],
  blocks: [
    {
      id: 'block-1',
      order_index: 0,
      page_number: 1,
      block_type: 'heading',
      source_text: 'Introduction',
      translated_text: '標題：Introduction',
      formula_latex: null,
      page_image_url: '/api/documents/doc-1/pages/1/image',
      section_path: 'Introduction',
      confidence: 1
    },
    {
      id: 'block-2',
      order_index: 1,
      page_number: 1,
      block_type: 'paragraph',
      source_text: 'Expected return is uncertain.',
      translated_text: '繁中翻譯：Expected return is uncertain.',
      formula_latex: null,
      page_image_url: '/api/documents/doc-1/pages/1/image',
      section_path: 'Introduction',
      confidence: 1
    },
    {
      id: 'block-3',
      order_index: 2,
      page_number: 2,
      block_type: 'formula',
      source_text: 'E[R] = rf + beta * (rm - rf)\nVar(R) = sigma^2',
      translated_text: '公式：E[R] = rf + beta * (rm - rf)\nVar(R) = sigma^2',
      formula_latex: String.raw`\mathbb{E}[R] = r_f + \beta(r_m-r_f)`,
      page_image_url: '/api/documents/doc-1/pages/2/image',
      section_path: 'Introduction',
      confidence: 1
    },
    {
      id: 'block-4',
      order_index: 3,
      page_number: 2,
      block_type: 'figure',
      source_text: 'Figure 1.1 Payoff diagram',
      translated_text: '圖表：Figure 1.1 Payoff diagram',
      formula_latex: null,
      page_image_url: '/api/documents/doc-1/pages/2/image',
      section_path: 'Introduction',
      confidence: 1
    }
  ]
}

describe('Reader', () => {
  it('renders aligned source and translation rows with synchronized hover', () => {
    render(<Reader payload={payload} />)

    const row = screen.getByTestId('reader-row-block-2')
    expect(within(row).getByText('Expected return is uncertain.')).toBeInTheDocument()
    expect(within(row).getByText('繁中翻譯：Expected return is uncertain.')).toBeInTheDocument()
    expect(screen.getByText('Introduction 的重點摘要。')).toBeInTheDocument()

    fireEvent.mouseEnter(row)

    expect(row).toHaveAttribute('data-hovered', 'true')
  })

  it('typesets formula blocks instead of showing raw LaTeX in a preformatted box', () => {
    render(<Reader payload={payload} />)

    const formulaRow = screen.getByTestId('reader-row-block-3')
    expect(formulaRow).toHaveAttribute('data-block-type', 'formula')
    expect(formulaRow.querySelectorAll('.katex')).toHaveLength(2)
    expect(formulaRow.querySelector('pre')).not.toBeInTheDocument()
    expect(within(formulaRow).getAllByRole('link', { name: 'View original page 2' })[0]).toHaveAttribute(
      'href',
      '/api/documents/doc-1/pages/2/image'
    )

    const figureRow = screen.getByTestId('reader-row-block-4')
    expect(figureRow).toHaveAttribute('data-block-type', 'figure')
    expect(within(figureRow).getByText('Figure 1.1 Payoff diagram')).toBeInTheDocument()
  })

  it('keeps figure blocks linked to their original page', () => {
    render(<Reader payload={payload} />)

    const figureRow = screen.getByTestId('reader-row-block-4')
    expect(figureRow).toHaveAttribute('data-block-type', 'figure')
    expect(within(figureRow).getByText('Figure 1.1 Payoff diagram')).toBeInTheDocument()
  })

  it('renders every supplied block so variable-height rows cannot skip content', () => {
    const manyBlocks: ReaderPayload = {
      ...payload,
      blocks: Array.from({ length: 95 }, (_, index) => ({
        id: `block-${index}`,
        order_index: index,
        page_number: 1,
        block_type: 'paragraph',
        source_text: `Source block ${index}`,
        translated_text: `繁中翻譯：Source block ${index}`,
        formula_latex: null,
        page_image_url: '/api/documents/doc-1/pages/1/image',
        section_path: 'Introduction',
        confidence: 1
      }))
    }

    render(<Reader payload={manyBlocks} />)

    expect(screen.getByTestId('reader-row-block-94')).toBeInTheDocument()
  })

  it('warns when the reader is an older snapshot of a changed source', () => {
    render(
      <Reader
        payload={{
          ...payload,
          document: { ...payload.document, status: 'stale' }
        }}
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      'This reader was generated from an older source version. Reprocess the document to update it.'
    )
  })

  it('focuses exact map evidence, identifies citing nodes, and returns to the Map', () => {
    const onReturnToMap = vi.fn()
    render(
      <Reader
        payload={payload}
        focusBlockId="block-2"
        citingNodes={[{ id: 'node-1', title: 'Primary result' }]}
        onReturnToMap={onReturnToMap}
      />
    )

    const focused = screen.getByTestId('reader-row-block-2')
    expect(focused).toHaveFocus()
    expect(focused).toHaveAttribute('aria-current', 'location')
    expect(within(focused).getByText('Cited by Primary result')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Return to Research Map' }))
    expect(onReturnToMap).toHaveBeenCalledTimes(1)
  })
})
