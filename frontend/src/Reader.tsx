import {
  ArrowLeft,
  FileImage,
  FileText,
  Gauge,
  ListTree,
  SquareFunction,
  Table2
} from 'lucide-react'
import katex from 'katex'
import { useEffect, useMemo, useState } from 'react'
import 'katex/dist/katex.min.css'

import type { ReaderBlock, ReaderPayload } from './types'

type ReaderProps = {
  payload: ReaderPayload
  focusBlockId?: string | null
  citingNodes?: Array<{ id: string; title: string }>
  onReturnToMap?: () => void
}

export function Reader({
  payload,
  focusBlockId = null,
  citingNodes = [],
  onReturnToMap
}: ReaderProps) {
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null)

  const firstBlockBySectionPath = useMemo(() => {
    const targets = new Map<string, string>()
    for (const block of payload.blocks) {
      if (block.section_path && !targets.has(block.section_path)) {
        targets.set(block.section_path, block.id)
      }
    }
    return targets
  }, [payload.blocks])

  useEffect(() => {
    if (!focusBlockId) return
    document.getElementById(`block-${focusBlockId}`)?.focus({ preventScroll: true })
  }, [focusBlockId, payload.document.id])

  return (
    <section className="reader-shell" aria-label={`Reader for ${payload.document.title}`}>
      <aside className="section-rail" aria-label="Sections">
        <div className="rail-header">
          <ListTree aria-hidden="true" size={18} />
          <span>Sections</span>
        </div>
        <div className="summary-block">
          <p className="kicker">Overview</p>
          <p>{payload.summary}</p>
        </div>
        <nav className="section-list">
          {payload.sections.map((section) => (
            <a href={`#block-${firstBlockBySectionPath.get(section.path) ?? section.id}`} key={section.id}>
              <span title={section.title}>{compactText(section.title, 52)}</span>
              <span className="progress-pill">{Math.round(section.progress)}%</span>
              <small>{compactText(section.summary, 92)}</small>
            </a>
          ))}
        </nav>
      </aside>

      <div className="reader-main">
        <header className="reader-header">
          <div>
            <p className="kicker">Aligned reading</p>
            <h2>{payload.document.title}</h2>
          </div>
          <div className="reader-header-actions">
            {onReturnToMap ? (
              <button type="button" className="text-button" onClick={onReturnToMap}>
                <ArrowLeft aria-hidden="true" size={16} /> Return to Research Map
              </button>
            ) : null}
            <div className="reader-stat">
              <Gauge aria-hidden="true" size={18} />
              <span>{payload.blocks.length} blocks</span>
            </div>
          </div>
        </header>

        {payload.document.status === 'stale' ? (
          <p className="reader-warning" role="alert">
            This reader was generated from an older source version. Reprocess the document to update
            it.
          </p>
        ) : null}

        <div className="block-table">
          <div className="block-grid block-grid-head" aria-hidden="true">
            <span>Source</span>
            <span>繁體中文</span>
          </div>
          {payload.blocks.map((block) => (
            <ReaderRow
              block={block}
              hovered={hoveredBlockId === block.id}
              focused={focusBlockId === block.id}
              citingNodes={focusBlockId === block.id ? citingNodes : []}
              key={block.id}
              onHover={setHoveredBlockId}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

type ReaderRowProps = {
  block: ReaderBlock
  hovered: boolean
  focused: boolean
  citingNodes: Array<{ id: string; title: string }>
  onHover: (blockId: string | null) => void
}

function ReaderRow({ block, hovered, focused, citingNodes, onHover }: ReaderRowProps) {
  return (
    <article
      className="block-grid reader-row"
      data-block-type={block.block_type}
      data-hovered={hovered ? 'true' : 'false'}
      data-focused={focused ? 'true' : 'false'}
      data-testid={`reader-row-${block.id}`}
      id={`block-${block.id}`}
      tabIndex={-1}
      aria-current={focused ? 'location' : undefined}
      onMouseEnter={() => onHover(block.id)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="source-cell">
        {citingNodes.length ? <CitationBadges nodes={citingNodes} /> : null}
        <BlockMeta block={block} />
        <BlockContent block={block} side="source" />
      </div>
      <div className="translation-cell">
        <BlockMeta block={block} />
        <BlockContent block={block} side="translation" />
      </div>
    </article>
  )
}

function CitationBadges({ nodes }: { nodes: Array<{ id: string; title: string }> }) {
  return (
    <div className="citation-badges" aria-label="Research Map citations">
      {nodes.map((node) => <span key={node.id}>Cited by {node.title}</span>)}
    </div>
  )
}

function BlockMeta({ block }: { block: ReaderBlock }) {
  const Icon = blockIcon(block.block_type)
  return (
    <div className="block-meta">
      <Icon aria-hidden="true" size={13} />
      <span>p.{block.page_number}</span>
      <span>{block.block_type}</span>
      {block.section_path ? <span>{compactText(block.section_path, 42)}</span> : null}
      <a href={block.page_image_url} rel="noreferrer" target="_blank">
        View original page {block.page_number}
      </a>
    </div>
  )
}

function BlockContent({ block, side }: { block: ReaderBlock; side: 'source' | 'translation' }) {
  const text = side === 'source' ? block.source_text : block.translated_text
  if (block.block_type === 'formula') {
    return (
      <div className="formula-reading-object">
        <MathFormula fallback={block.source_text} latex={block.formula_latex} />
        {side === 'translation' ? <p className="formula-explanation">{text}</p> : null}
        {side === 'source' ? (
          <details className="formula-source-details">
            <summary>OCR source</summary>
            <p>{text}</p>
          </details>
        ) : null}
      </div>
    )
  }
  if (block.block_type === 'figure' || block.block_type === 'table') {
    return (
      <div className="visual-reference">
        <p>{text}</p>
        <a href={block.page_image_url} rel="noreferrer" target="_blank">
          View original page {block.page_number}
        </a>
      </div>
    )
  }
  return <p className="block-text">{text}</p>
}

function MathFormula({ fallback, latex }: { fallback: string; latex: string | null }) {
  if (!latex) {
    return (
      <div className="formula-render-error" role="note">
        <strong>Formula is not typeset yet.</strong>
        <span>{fallback}</span>
      </div>
    )
  }

  try {
    const markup = katex.renderToString(latex, {
      displayMode: true,
      output: 'htmlAndMathml',
      strict: false,
      throwOnError: true
    })
    return <div className="math-formula" dangerouslySetInnerHTML={{ __html: markup }} />
  } catch {
    return (
      <div className="formula-render-error" role="note">
        <strong>Formula could not be typeset.</strong>
        <span>{fallback}</span>
      </div>
    )
  }
}

function blockIcon(blockType: string) {
  if (blockType === 'formula') return SquareFunction
  if (blockType === 'figure') return FileImage
  if (blockType === 'table') return Table2
  return FileText
}

function compactText(text: string, maxLength: number) {
  const compacted = text.replace(/\s+/g, ' ').trim()
  if (compacted.length <= maxLength) return compacted
  return `${compacted.slice(0, Math.max(0, maxLength - 1)).trim()}…`
}
