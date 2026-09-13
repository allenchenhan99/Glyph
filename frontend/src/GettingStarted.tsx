import { useCallback, useEffect, useRef, useState } from 'react'
import { getWorkspaceStatus } from './api'
import type { DocumentRecord, WorkspaceStatus } from './types'

const GUIDE_KEY = 'glyph.getting-started.hidden'

export function useWorkspaceStatus() {
  const [data, setData] = useState<WorkspaceStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const sequence = useRef(0)
  const reload = useCallback(async () => {
    const request = ++sequence.current
    setError(null)
    try {
      const status = await getWorkspaceStatus()
      if (request === sequence.current) setData(status)
    } catch {
      if (request === sequence.current) setError('Could not load workspace setup. Check that the Glyph backend is running and inspect its startup terminal, then retry.')
    }
  }, [])
  useEffect(() => { void reload(); return () => { sequence.current += 1 } }, [reload])
  return { data, error, reload }
}

type Props = {
  workspace: WorkspaceStatus
  documents: DocumentRecord[]
  onSettings: () => void
  onUpload: () => void
  onRead: (document: DocumentRecord) => void
  onMap: (document: DocumentRecord) => void
  onContract: (document: DocumentRecord) => void
}

export function GettingStarted({ workspace, documents, onSettings, onUpload, onRead, onMap, onContract }: Props) {
  const [hidden, setHidden] = useState(() => {
    try { return window.localStorage.getItem(GUIDE_KEY) === 'true' } catch { return false }
  })
  const readable = documents.find(document => ['completed', 'stale', 'missing'].includes(document.status))
  const researchDocument = documents.find(document => document.status === 'completed' || document.research_map)
  const contractDocument = documents.find(document => document.implementation_contract)

  function toggle() {
    setHidden(!hidden)
    try { window.localStorage.setItem(GUIDE_KEY, String(!hidden)) } catch { /* Browsing without storage remains supported. */ }
  }

  return <section className="getting-started" aria-label="Getting started">
    {workspace.development_features.length ? <p className="development-label" role="note">
      Deterministic development output: {workspace.development_features.map(name => name.replaceAll('_', ' ')).join(', ')}. Choose real providers for model output.
    </p> : null}
    <div className="guide-heading">
      <p className="kicker">Your next steps</p>
      <button type="button" className="text-button" aria-expanded={!hidden} aria-controls="getting-started-steps" onClick={toggle}>
        {hidden ? 'Show getting started' : 'Hide getting started'}
      </button>
    </div>
    {!hidden ? <div id="getting-started-steps">
      <h2>{documents.length ? 'Continue your research' : 'Start with one document'}</h2>
      <p>{documents.length ? 'Your existing documents and reviews stay available below.' : 'Try a public text PDF first. Upload it here, or place it in book/ and select Refresh.'}</p>
      <div className="provider-overview">
        <div><strong>Translation: {workspace.translation.provider}</strong><p>{workspace.translation.message}</p></div>
        <div><strong>Research: {workspace.research.provider}</strong><p>{workspace.research.message}</p><small>Used by summaries, Research Maps and Implementation Contracts.</small></div>
        <div><strong>Document extraction</strong><p>{workspace.ocr.message}</p></div>
      </div>
      <ol className="getting-started-steps">
        <li><h3>Choose providers</h3><p>Local configuration checks do not verify sign-in or model access.</p>
          <button type="button" className="text-button" onClick={onSettings}>Choose translation provider</button>
          {!workspace.research.configured ? <p>Configure GLYPH_AI_MODE in .env and restart Glyph for research features.</p> : null}
        </li>
        <li><h3>Import and process</h3><p>Process checks readiness and creates an aligned Reader. Scans need OCR.</p>
          <button type="button" className="text-button" onClick={onUpload}>{documents.length ? 'Upload another document' : 'Upload your first document'}</button>
          {documents.length && !readable ? <p>Select Process beside your document below.</p> : null}
        </li>
        <li><h3>Read and inspect evidence</h3><p>Open Full Reader for translation and summaries. Research Map connects claims to their sources.</p>
          {readable ? <button type="button" className="text-button" onClick={() => onRead(readable)}>Continue reading {readable.title}</button> : null}
          {researchDocument ? <button type="button" className="text-button" onClick={() => onMap(researchDocument)}>Continue research for {researchDocument.title}</button> : null}
        </li>
        <li><h3>Define the implementation</h3><p>From a current Research Map, choose Build Implementation Contract. Review assumptions and evidence before exporting.</p>
          {contractDocument ? <button type="button" className="text-button" onClick={() => onContract(contractDocument)}>Continue contract for {contractDocument.title}</button> : null}
        </li>
      </ol>
    </div> : null}
  </section>
}
