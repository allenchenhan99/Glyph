import { useCallback, useEffect, useRef, useState } from 'react'
import { generateDocumentSummaries, getDocumentSummaries } from './api'
import type { DocumentSummaries, SummaryClaim } from './types'

type SummaryPanelProps = {
  documentId: string
  blockIds: string[]
  onNavigate: (blockId: string) => void
  pollInterval?: number
  canGenerate?: boolean
}

export function SummaryPanel({ documentId, blockIds, onNavigate, pollInterval = 1500, canGenerate = true }: SummaryPanelProps) {
  const [result, setResult] = useState<DocumentSummaries | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  const requestSequence = useRef(0)
  const busyRef = useRef(false)
  const blockIdentity = blockIds.join('\0')

  const request = useCallback(async (generate = false) => {
    if (generate && busyRef.current) return
    if (!generate && busyRef.current) return
    const epoch = generation.current
    const sequence = ++requestSequence.current
    if (generate) { busyRef.current = true; setBusy(true) }
    setError(null)
    try {
      const next = await (generate ? generateDocumentSummaries(documentId) : getDocumentSummaries(documentId))
      if (epoch === generation.current && sequence === requestSequence.current) setResult(next)
    } catch (cause) {
      if (epoch === generation.current && sequence === requestSequence.current) {
        setError(cause instanceof Error ? cause.message : 'Could not load summaries.')
      }
    } finally {
      if (generate && epoch === generation.current) { busyRef.current = false; setBusy(false) }
    }
  }, [documentId])

  useEffect(() => {
    generation.current += 1
    setResult(null)
    setError(null)
    setBusy(false)
    busyRef.current = false
    void request()
    return () => { generation.current += 1 }
  }, [request, blockIdentity])

  useEffect(() => {
    if (result?.status !== 'generating' || busy || error) return
    const timer = window.setTimeout(() => { void request() }, pollInterval)
    return () => window.clearTimeout(timer)
  }, [result, busy, error, pollInterval, request])

  const version = result?.version
  const claims = version?.claims ?? []
  const sectionPaths = [...new Set(claims.map(claim => claim.section_path))]
  const missingBlocks = claims.some(claim => claim.evidence.some(anchor => !blockIds.includes(anchor.block_id)))
  const running = busy || result?.status === 'generating'
  const retained = version && (result?.status === 'failed' || running)
  return (
    <section className="summary-panel" aria-label="Evidence-linked summary">
      <p className="kicker">Summary</p>
      {!result && !error ? <p role="status">Loading summary…</p> : null}
      {error ? <div role="alert"><p>{error}</p><button className="text-button" type="button" onClick={() => void request()}>Reload summaries</button></div> : null}
      {result ? <>
        <p className="summary-provider">Summary provider: {result.provider}{result.model ? ` · ${result.model}` : ''}</p>
        {result.provider === 'mock' || version?.provider === 'mock' ?
          <p className="summary-notice">Development output · deterministic source excerpts.</p> : null}
        {result.status === 'not_generated' ? <p>No summary generated yet.</p> : null}
        {running ? <p role="status">Generating summary… You can leave and return.</p> : null}
        {result.status === 'failed' ? <p role="alert">{result.job?.error_message ?? 'Summary generation failed. Try again.'}</p> : null}
        {retained ? <p className="summary-notice">Previous summary retained.</p> : null}
        {result.status === 'stale' || missingBlocks ? <p className="summary-notice" role="note">This summary belongs to a different Reader version. Retained quotes remain available; generate again from the current Full Reader.</p> : null}
        {version ? <>
          <p className="summary-notice">AI draft · check claims against the cited source. Matching quotes do not verify the interpretation.</p>
          {version.provider !== result.provider ? <p className="summary-provider">Saved version: {version.provider}</p> : null}
          {sectionPaths.map(path => <div className="summary-claim-group" key={path ?? '__overview'}>
            <h3>{path ?? 'Overview'}</h3>
            {claims.filter(claim => claim.section_path === path).map(claim =>
              <Claim key={claim.id} claim={claim} blockIds={blockIds} onNavigate={onNavigate} />)}
          </div>)}
        </> : null}
        {canGenerate ? <button type="button" className="text-button summary-generate" disabled={running}
          onClick={() => void request(true)}>
          {running ? 'Generating…' : result.status === 'failed' ? 'Retry summary' : version ? 'Regenerate summary' : 'Generate summary'}
        </button> : <p className="summary-provider">Open Full Reader to generate a summary of the current document.</p>}
        {!running && canGenerate ? <p className="summary-provider">Generation sends Reader text to the selected summary provider.</p> : null}
      </> : null}
    </section>
  )
}

function Claim({ claim, blockIds, onNavigate }: { claim: SummaryClaim; blockIds: string[]; onNavigate: (id: string) => void }) {
  return <details className="summary-claim">
    <summary>{claim.text}</summary>
    {claim.evidence.map((anchor, index) => <div className="summary-evidence" key={`${anchor.block_id}:${index}`}>
      <blockquote>{anchor.quote_text}</blockquote>
      {blockIds.includes(anchor.block_id) ?
        <button type="button" className="text-button" onClick={() => onNavigate(anchor.block_id)}>Go to source page {anchor.page_number}</button> :
        <span className="summary-provider">Page {anchor.page_number} · retained quotation</span>}
    </div>)}
  </details>
}
