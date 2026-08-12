import { BookOpenText, Check, HelpCircle, PencilLine, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { provenanceLabel, qualityLabel, relationLabel } from './GuidedReview'
import type { ResearchNode, ReviewStatus } from './types'

type EvidenceInspectorProps = {
  node: ResearchNode
  onClose: () => void
  onOpenReader: (blockId: string) => void
  onReview: (
    status: ReviewStatus,
    correctedClaimText: string | null,
    reviewNote: string | null
  ) => void
}

export function EvidenceInspector({
  node,
  onClose,
  onOpenReader,
  onReview
}: EvidenceInspectorProps) {
  const [correctedClaim, setCorrectedClaim] = useState('')
  const [reviewNote, setReviewNote] = useState('')

  useEffect(() => {
    setCorrectedClaim(node.review?.corrected_claim_text ?? '')
    setReviewNote(node.review?.review_note ?? '')
  }, [node.id, node.review?.id, node.review?.corrected_claim_text, node.review?.review_note])

  const optionalNote = reviewNote.trim() || null

  return (
    <aside className="evidence-inspector" aria-label={`Evidence Inspector for ${node.title}`}>
      <header className="inspector-header">
        <div>
          <p className="kicker">Evidence Inspector</p>
          <h2>{node.title}</h2>
        </div>
        <button type="button" className="bare-icon-button" onClick={onClose} aria-label="Close Evidence Inspector">
          <X aria-hidden="true" size={18} />
        </button>
      </header>

      <section className="inspector-claim" aria-label="Effective claim">
        <p className="field-label">Current reviewed claim</p>
        <p>{node.effective_claim_text}</p>
        <div className="claim-tags">
          <span>{provenanceLabel(node.provenance)}</span>
          <span>{qualityLabel(node.evidence_quality)}</span>
        </div>
        {node.effective_claim_text !== node.claim_text ? (
          <details>
            <summary>Original AI draft</summary>
            <p>{node.claim_text}</p>
          </details>
        ) : null}
      </section>

      <div className="evidence-stack">
        {node.evidence.length ? (
          node.evidence.map((item, index) => (
            <article className="evidence-anchor" key={item.id}>
              <div className="anchor-number" aria-hidden="true">E{String(index + 1).padStart(2, '0')}</div>
              <p className="field-label">Verbatim English</p>
              <blockquote>{item.quote_text}</blockquote>
              <p className="field-label">繁體中文區塊翻譯</p>
              <p className="translated-evidence" lang="zh-Hant">{item.translated_text}</p>
              <p className="locator-line">
                Page {item.page_number} · {locatorLabel(item.locator_type)} · {relationLabel(item.relation)}
                {item.source_label ? ` · ${item.source_label}` : ''}
              </p>
              <button
                type="button"
                className="reader-link"
                onClick={() => onOpenReader(item.block_id)}
                aria-label="View evidence in Reader"
              >
                <BookOpenText aria-hidden="true" size={16} /> View in Reader
              </button>
            </article>
          ))
        ) : (
          <p className="evidence-empty" role="note">No exact source anchor is available for this claim.</p>
        )}
      </div>

      <section className="human-review" aria-labelledby="human-review-title">
        <p className="kicker">Human layer</p>
        <h3 id="human-review-title">Review without erasing the draft</h3>
        <label>
          Review note <span>(optional)</span>
          <textarea value={reviewNote} onChange={(event) => setReviewNote(event.currentTarget.value)} />
        </label>
        <div className="review-actions">
          <button type="button" onClick={() => onReview('confirmed', null, optionalNote)} aria-label="Confirm claim">
            <Check aria-hidden="true" size={16} /> Confirm
          </button>
          <button type="button" onClick={() => onReview('questioned', null, optionalNote)} aria-label="Question claim">
            <HelpCircle aria-hidden="true" size={16} /> Question
          </button>
        </div>
        <label>
          Corrected claim
          <textarea
            value={correctedClaim}
            onChange={(event) => setCorrectedClaim(event.currentTarget.value)}
            aria-label="Corrected claim"
          />
        </label>
        <button
          type="button"
          className="save-correction"
          disabled={!correctedClaim.trim()}
          onClick={() => onReview('corrected', correctedClaim.trim(), optionalNote)}
          aria-label="Save correction"
        >
          <PencilLine aria-hidden="true" size={16} /> Save correction
        </button>
      </section>
    </aside>
  )
}

function locatorLabel(value: ResearchNode['evidence'][number]['locator_type']): string {
  if (value === 'text_span') return 'Text span'
  return value.charAt(0).toUpperCase() + value.slice(1)
}
