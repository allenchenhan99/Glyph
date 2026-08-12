import { BookOpenText, LockKeyhole, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import {
  contractItemTypeLabel,
  contractOriginLabel,
  contractValueLabel
} from './contractPresentation'
import type { ContractNotice } from './implementationContractState'
import type {
  ContractResolutionStatus,
  ContractValue,
  ImplementationContractItem
} from './types'

type ContractInspectorProps = {
  item: ImplementationContractItem
  pending?: boolean
  notice: ContractNotice
  onClose: () => void
  onOpenReader: (blockId: string) => void
  onResolve: (
    status: ContractResolutionStatus,
    resolvedValue: ContractValue | null,
    reason: string | null
  ) => void
  onRemainBlocked: () => void
  onOpenMapNode?: (nodeId: string) => void
}

export function ContractInspector({
  item,
  pending = false,
  notice,
  onClose,
  onOpenReader,
  onResolve,
  onRemainBlocked,
  onOpenMapNode
}: ContractInspectorProps) {
  const [decisionValue, setDecisionValue] = useState('')
  const [decisionReason, setDecisionReason] = useState('')
  const [validation, setValidation] = useState<string | null>(null)
  const validationId = `contract-decision-validation-${item.id}`
  const noticeId = `contract-decision-notice-${item.id}`
  const isMissing = item.origin === 'missing'
  const canMarkNotApplicable = isMissing && item.is_optional
  const canRecordGrossReplication = isMissing && item.item_type === 'transaction_cost'
  const linkedResearchNodeId =
    item.evidence.find((evidence) => evidence.research_node_id !== null)?.research_node_id ?? null

  useEffect(() => {
    setDecisionValue('')
    setDecisionReason('')
    setValidation(null)
  }, [item.id])

  function saveDecision() {
    const value = decisionValue.trim()
    const reason = decisionReason.trim()
    if (!value) {
      setValidation('Enter the implementation value chosen for this item.')
      return
    }
    if (!reason) {
      setValidation('Explain why this decision is appropriate.')
      return
    }
    setValidation(null)
    onResolve('decided', { kind: 'scalar', value }, reason)
  }

  function markNotApplicable() {
    const reason = decisionReason.trim()
    if (!reason) {
      setValidation('Explain why this item is not applicable.')
      return
    }
    setValidation(null)
    onResolve('not_applicable', null, reason)
  }

  function recordGrossReplication() {
    const reason = decisionReason.trim()
    if (!reason) {
      setValidation('Explain why gross replication is appropriate.')
      return
    }
    setValidation(null)
    onResolve('decided', { kind: 'scalar', value: 'gross_replication' }, reason)
  }

  function confirmSupported() {
    setValidation(null)
    onResolve('confirmed', null, decisionReason.trim() || null)
  }

  function questionSupported() {
    setValidation(null)
    onResolve('questioned', null, decisionReason.trim() || null)
  }

  function saveCorrection() {
    const value = decisionValue.trim()
    const reason = decisionReason.trim()
    if (!value) {
      setValidation('Enter the corrected implementation value.')
      return
    }
    if (!reason) {
      setValidation('Explain why the supported value needs correction.')
      return
    }
    setValidation(null)
    onResolve('corrected', { kind: 'scalar', value }, reason)
  }

  const describedBy = [validation ? validationId : null, notice ? noticeId : null]
    .filter(Boolean)
    .join(' ') || undefined

  return (
    <aside
      className="contract-inspector"
      aria-label={`Contract Inspector for ${contractItemTypeLabel(item.item_type)}`}
    >
      <header className="inspector-header">
        <div>
          <p className="kicker">Contract Inspector</p>
          <h2>{contractItemTypeLabel(item.item_type)}</h2>
        </div>
        <button
          type="button"
          className="bare-icon-button"
          onClick={onClose}
          aria-label="Close Contract Inspector"
        >
          <X aria-hidden="true" size={18} />
        </button>
      </header>

      <section className="contract-inspector-value" aria-label="Contract value provenance">
        <span className={`contract-origin origin-${item.effective_origin}`}>
          {contractOriginLabel(item.effective_origin)}
        </span>
        <dl>
          <div>
            <dt>Draft</dt>
            <dd>{contractValueLabel(item.draft_value)}</dd>
          </div>
          <div>
            <dt>Effective</dt>
            <dd>{contractValueLabel(item.effective_value)}</dd>
          </div>
        </dl>
        {item.rationale ? (
          <div className="contract-rationale">
            <p className="field-label">Derivation rationale</p>
            <p>{item.rationale}</p>
          </div>
        ) : null}
      </section>

      {item.effective_origin === 'human_decision' && item.resolution ? (
        <section className="contract-decision-history" aria-label="Human decision history">
          <p className="field-label">Current decision reason</p>
          <p>{item.resolution.reason}</p>
          <ol>
            {item.resolution_history.map((resolution) => (
              <li key={resolution.id}>
                <strong>Revision {resolution.revision_number} · {resolution.status}</strong>
                {resolution.reason ? <span>{resolution.reason}</span> : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <div className="contract-evidence-stack">
        {item.evidence.map((evidence, index) => (
          <article className="evidence-anchor" key={evidence.id}>
            <div className="anchor-number" aria-hidden="true">
              E{String(index + 1).padStart(2, '0')}
            </div>
            <p className="field-label">Verbatim English</p>
            <blockquote>{evidence.quote_text}</blockquote>
            <p className="field-label">繁體中文區塊翻譯</p>
            <p className="translated-evidence" lang="zh-Hant">
              {evidence.translated_text}
            </p>
            <p className="locator-line">
              Page {evidence.page_number} · {evidence.locator_type} · {evidence.relation}
            </p>
            <button
              type="button"
              className="reader-link"
              disabled={pending}
              onClick={() => onOpenReader(evidence.block_id)}
              aria-label={`Open evidence E${String(index + 1).padStart(2, '0')} in Reader`}
            >
              <BookOpenText aria-hidden="true" size={16} /> Open in Reader
            </button>
          </article>
        ))}
      </div>

      {linkedResearchNodeId && onOpenMapNode ? (
        <button
          type="button"
          className="reader-link contract-map-link"
          disabled={pending}
          onClick={() => onOpenMapNode(linkedResearchNodeId)}
          aria-label="Open linked Research Map node"
        >
          Open linked Research Map node
        </button>
      ) : null}

      {notice ? (
        <p
          id={noticeId}
          className={notice.kind === 'error' ? 'map-alert' : 'map-status'}
          role={notice.kind === 'error' ? 'alert' : 'status'}
        >
          {notice.message}
        </p>
      ) : null}

      {isMissing ? (
        <fieldset
          className="contract-decision-form"
          disabled={pending}
          aria-describedby={describedBy}
        >
          <legend>Resolve missing implementation value</legend>
          <p>
            Glyph will not infer a default. Keep the blocker or record a reasoned desk decision.
            Optional items alone may be marked not applicable.
          </p>
          <label>
            Decision value
            <input
              name={`contract-item-${item.id}-value`}
              value={decisionValue}
              onChange={(event) => setDecisionValue(event.currentTarget.value)}
              aria-invalid={validation?.startsWith('Enter the implementation') || undefined}
            />
          </label>
          <label>
            Decision reason
            <textarea
              name={`contract-item-${item.id}-reason`}
              value={decisionReason}
              onChange={(event) => setDecisionReason(event.currentTarget.value)}
              aria-invalid={validation?.startsWith('Explain') || undefined}
              aria-describedby={validation ? validationId : undefined}
            />
          </label>
          {validation ? (
            <p id={validationId} className="contract-form-error" role="alert">
              {validation}
            </p>
          ) : null}
          <div className="contract-decision-actions">
            <button type="button" onClick={onRemainBlocked} aria-label="Keep item blocked">
              <LockKeyhole aria-hidden="true" size={16} /> Keep blocked
            </button>
            <button type="button" onClick={saveDecision} aria-label="Save human decision">
              Save decision
            </button>
            {canMarkNotApplicable ? (
              <button
                type="button"
                onClick={markNotApplicable}
                aria-label="Mark item not applicable"
              >
                Not applicable
              </button>
            ) : null}
            {canRecordGrossReplication ? (
              <button
                type="button"
                onClick={recordGrossReplication}
                aria-label="Record gross replication"
              >
                Gross replication
              </button>
            ) : null}
          </div>
          <button
            type="button"
            className="reader-link"
            onClick={() => onOpenReader(item.evidence[0]?.block_id ?? '')}
            aria-label="Open Reader to investigate"
          >
            <BookOpenText aria-hidden="true" size={16} /> Open Reader to investigate
          </button>
        </fieldset>
      ) : (
        <fieldset
          className="contract-decision-form"
          disabled={pending}
          aria-describedby={describedBy}
        >
          <legend>Review supported implementation value</legend>
          <p>Confirm the source-backed value, question it, or save a reasoned correction.</p>
          <label>
            Corrected value
            <input
              name={`contract-item-${item.id}-value`}
              value={decisionValue}
              onChange={(event) => setDecisionValue(event.currentTarget.value)}
              aria-invalid={validation?.startsWith('Enter the corrected') || undefined}
            />
          </label>
          <label>
            Review reason
            <textarea
              name={`contract-item-${item.id}-reason`}
              value={decisionReason}
              onChange={(event) => setDecisionReason(event.currentTarget.value)}
              aria-invalid={validation?.startsWith('Explain') || undefined}
              aria-describedby={validation ? validationId : undefined}
            />
          </label>
          {validation ? (
            <p id={validationId} className="contract-form-error" role="alert">
              {validation}
            </p>
          ) : null}
          <div className="contract-decision-actions">
            <button type="button" onClick={confirmSupported} aria-label="Confirm supported item">
              Confirm
            </button>
            <button type="button" onClick={questionSupported} aria-label="Question supported item">
              Question
            </button>
            <button
              type="button"
              onClick={saveCorrection}
              aria-label="Save supported-item correction"
            >
              Save correction
            </button>
          </div>
        </fieldset>
      )}
    </aside>
  )
}
