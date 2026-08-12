import { BookOpen, FileSearch, FileUp, Loader2, Play, RefreshCw } from 'lucide-react'
import { useEffect, useReducer, useRef, useState } from 'react'

import {
  ApiError,
  enqueueResearchMap,
  getActiveResearchMap,
  getReader,
  getResearchMapJob,
  listDocuments,
  processDocument,
  reviewResearchNode,
  uploadDocument
} from './api'
import { Reader } from './Reader'
import { ResearchMap } from './ResearchMap'
import {
  initialResearchMapState,
  pollResearchMapJob,
  researchMapReducer
} from './researchMapState'
import type {
  DocumentRecord,
  ReaderPayload,
  ResearchNodeReview,
  ReviewStatus
} from './types'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'
type Notice = { kind: 'status' | 'error'; message: string } | null

export function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [notice, setNotice] = useState<Notice>(null)
  const [reader, setReader] = useState<ReaderPayload | null>(null)
  const [activeDocument, setActiveDocument] = useState<DocumentRecord | null>(null)
  const [mapState, dispatchMap] = useReducer(researchMapReducer, initialResearchMapState)
  const pollController = useRef<AbortController | null>(null)

  useEffect(() => () => pollController.current?.abort(), [])

  async function refreshDocuments() {
    setLoadState('loading')
    try {
      setDocuments(await listDocuments())
      setLoadState('ready')
      setNotice(null)
    } catch (error) {
      console.error(error)
      setLoadState('error')
      setNotice({ kind: 'error', message: errorMessage(error, 'Could not load documents.') })
    }
  }

  useEffect(() => {
    void refreshDocuments()
  }, [])

  async function handleUpload(file: File | undefined) {
    if (!file) return
    setNotice({ kind: 'status', message: `Uploading ${file.name}` })
    try {
      await uploadDocument(file)
      await refreshDocuments()
    } catch (error) {
      console.error(error)
      setNotice({ kind: 'error', message: errorMessage(error, 'Upload failed.') })
    }
  }

  async function handleProcess(document: DocumentRecord) {
    setNotice({ kind: 'status', message: `Processing ${document.title}` })
    try {
      const job = await processDocument(document.id)
      await refreshDocuments()
      if (job.status !== 'completed') {
        setNotice({
          kind: 'error',
          message: job.error_message ?? `Processing failed for ${document.title}`
        })
        return
      }
      setNotice({ kind: 'status', message: `Processed ${document.title}` })
    } catch (error) {
      console.error(error)
      setNotice({
        kind: 'error',
        message: errorMessage(error, `Processing failed for ${document.title}`)
      })
    }
  }

  async function handleOpenReader(document: DocumentRecord) {
    setNotice({ kind: 'status', message: `Opening ${document.title}` })
    try {
      setActiveDocument(document)
      setReader(await getReader(document.id))
      dispatchMap({ type: 'openReader', blockId: '' })
      setNotice(null)
    } catch (error) {
      console.error(error)
      setNotice({
        kind: 'error',
        message: errorMessage(error, `Reader is not ready for ${document.title}`)
      })
    }
  }

  async function handleOpenMap(document: DocumentRecord) {
    pollController.current?.abort()
    setActiveDocument(document)
    setReader(null)
    dispatchMap({ type: 'resetWorkspace' })
    dispatchMap({ type: 'mapLoading' })
    try {
      dispatchMap({ type: 'mapLoaded', map: await getActiveResearchMap(document.id) })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        dispatchMap({ type: 'mapAbsent' })
        return
      }
      console.error(error)
      dispatchMap({
        type: 'mapFailed',
        message: errorMessage(error, `Could not load the Research Map for ${document.title}.`)
      })
    }
  }

  async function handleGenerateMap() {
    if (!activeDocument) return
    pollController.current?.abort()
    const controller = new AbortController()
    pollController.current = controller
    try {
      const queued = await enqueueResearchMap(activeDocument.id)
      dispatchMap({ type: 'jobUpdated', job: queued })
      const terminal = await pollResearchMapJob(queued.id, {
        fetchJob: getResearchMapJob,
        onJob: (job) => dispatchMap({ type: 'jobUpdated', job }),
        signal: controller.signal
      })
      if (terminal?.status === 'completed') {
        dispatchMap({ type: 'mapLoaded', map: await getActiveResearchMap(activeDocument.id) })
        await refreshDocuments()
      }
    } catch (error) {
      if (controller.signal.aborted) return
      console.error(error)
      dispatchMap({
        type: 'mapFailed',
        message: errorMessage(error, 'Could not generate the Research Map.')
      })
    }
  }

  async function handleMapEvidence(blockId: string) {
    if (!activeDocument) return
    try {
      setReader(await getReader(activeDocument.id))
      dispatchMap({ type: 'openReader', blockId })
    } catch (error) {
      console.error(error)
      dispatchMap({
        type: 'mapFailed',
        message: errorMessage(error, 'The cited Reader block could not be opened.')
      })
    }
  }

  async function handleReview(
    status: ReviewStatus,
    correctedClaimText: string | null,
    reviewNote: string | null
  ) {
    const node = mapState.map?.nodes.find((item) => item.id === mapState.selectedNodeId)
    if (!node) return
    const optimisticReview: ResearchNodeReview = {
      id: `optimistic-${node.id}`,
      status,
      corrected_claim_text: correctedClaimText,
      review_note: reviewNote,
      revision_number: (node.review?.revision_number ?? 0) + 1,
      supersedes_review_id: node.review?.id ?? null,
      reviewed_at: new Date().toISOString()
    }
    dispatchMap({ type: 'reviewOptimistic', nodeId: node.id, review: optimisticReview })
    try {
      const saved = await reviewResearchNode(node.id, {
        status,
        based_on_node_signature: node.node_signature,
        corrected_claim_text: correctedClaimText,
        review_note: reviewNote
      })
      dispatchMap({ type: 'reviewSaved', nodeId: node.id, review: saved })
      await refreshDocuments()
    } catch (error) {
      console.error(error)
      const message =
        error instanceof ApiError && error.status === 409
          ? `${error.message} Reload the Research Map and review it again.`
          : errorMessage(error, 'The review was not saved. Try again.')
      dispatchMap({ type: 'reviewConflict', message })
    }
  }

  return (
    <main className="app-shell">
      <section
        className={reader || activeDocument ? 'library-panel library-panel-compact' : 'library-panel'}
        aria-labelledby="library-title"
      >
        <div className="topbar">
          <div>
            <p className="kicker">Glyph study desk</p>
            <h1 id="library-title">Reading workspace</h1>
          </div>
          <div className="toolbar">
            <label className="icon-button">
              <FileUp aria-hidden="true" size={18} />
              <span>Upload</span>
              <input
                aria-label="Upload document"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(event) => void handleUpload(event.currentTarget.files?.[0])}
              />
            </label>
            <button type="button" className="icon-button" onClick={() => void refreshDocuments()}>
              <RefreshCw aria-hidden="true" size={18} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {notice ? (
          <p
            className={notice.kind === 'error' ? 'error-line' : 'status-line'}
            role={notice.kind === 'error' ? 'alert' : 'status'}
          >
            {notice.message}
          </p>
        ) : null}
        {loadState === 'loading' ? (
          <p className="status-line">
            <Loader2 aria-hidden="true" size={16} /> Loading documents
          </p>
        ) : null}

        <div className="document-list" aria-label="Documents">
          {documents.map((document) => (
            <article className="document-row" key={document.id}>
              <div className="document-main">
                <BookOpen aria-hidden="true" size={18} />
                <div>
                  <h2>{document.title}</h2>
                  <p>
                    {document.file_type.toUpperCase()} · {documentStatusLabel(document.status)}
                  </p>
                  {document.research_map ? (
                    <div className="library-map-summary" aria-label={`Research Map status for ${document.title}`}>
                      <span>{document.research_map.reviewed_core_nodes} / {document.research_map.reviewable_core_nodes} verified</span>
                      <span>{document.research_map.issue_count} evidence gap{document.research_map.issue_count === 1 ? '' : 's'}</span>
                      <span>{document.research_map.is_stale ? 'Stale' : 'Current'} · {document.research_map.status}</span>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="row-actions">
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => void handleProcess(document)}
                  aria-label={`Process ${document.title}`}
                >
                  <Play aria-hidden="true" size={16} />
                  <span>Process</span>
                </button>
                <button
                  type="button"
                  className="icon-button secondary"
                  onClick={() => void handleOpenMap(document)}
                  aria-label={`Open Research Map for ${document.title}`}
                >
                  <FileSearch aria-hidden="true" size={16} />
                  <span>Research Map</span>
                </button>
                <button
                  type="button"
                  className="icon-button tertiary"
                  onClick={() => void handleOpenReader(document)}
                  aria-label={`Open Full Reader for ${document.title}`}
                >
                  <BookOpen aria-hidden="true" size={16} />
                  <span>Full Reader</span>
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {activeDocument && mapState.mode === 'map' ? (
        mapState.loadStatus === 'loading' ? (
          <section className="workspace-loading" aria-label="Loading Research Map">
            <Loader2 aria-hidden="true" size={20} /> Loading Research Map
          </section>
        ) : (
          <ResearchMap
            map={mapState.map}
            selectedNodeId={mapState.selectedNodeId}
            guidedStep={mapState.guidedStep}
            inspectorOpen={mapState.inspectorOpen}
            notice={mapState.notice}
            job={mapState.job}
            onSelectNode={(nodeId) => dispatchMap({ type: 'selectNode', nodeId })}
            onOpenInspector={() => dispatchMap({ type: 'openInspector' })}
            onCloseInspector={() => dispatchMap({ type: 'closeInspector' })}
            onGuidedNext={() => dispatchMap({ type: 'guidedNext' })}
            onGuidedPrevious={() => dispatchMap({ type: 'guidedPrevious' })}
            onOpenReader={(blockId) => void handleMapEvidence(blockId)}
            onReview={(status, corrected, note) => void handleReview(status, corrected, note)}
            onGenerate={() => void handleGenerateMap()}
          />
        )
      ) : null}
      {reader && mapState.mode === 'reader' ? (
        <Reader
          payload={reader}
          focusBlockId={mapState.readerFocusBlockId || null}
          citingNodes={
            mapState.readerFocusBlockId
              ? (mapState.map?.nodes ?? [])
                  .filter((node) =>
                    node.evidence.some(
                      (evidence) => evidence.block_id === mapState.readerFocusBlockId
                    )
                  )
                  .map((node) => ({ id: node.id, title: node.title }))
              : []
          }
          onReturnToMap={mapState.map ? () => dispatchMap({ type: 'returnToMap' }) : undefined}
        />
      ) : null}
    </main>
  )
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

function documentStatusLabel(status: DocumentRecord['status']): string {
  switch (status) {
    case 'discovered':
      return 'Ready to process'
    case 'uploaded':
      return 'Uploaded · ready to process'
    case 'processing':
      return 'Processing'
    case 'completed':
      return 'Reader ready'
    case 'failed':
      return 'Processing failed · retry available'
    case 'stale':
      return 'Source changed — reprocess required'
    case 'missing':
      return 'Source file missing'
  }
}
