import { DocumentProcessing, useDocumentProcessing } from './DocumentProcessing'
import { SettingsPage } from './pages/SettingsPage'
import { BookOpen, FileSearch, FileUp, Loader2, RefreshCw } from 'lucide-react'
import { useEffect, useReducer, useRef, useState } from 'react'

import {
  ApiError,
  activateImplementationContract,
  enqueueImplementationContract,
  enqueueResearchMap,
  getActiveImplementationContract,
  getActiveResearchMap,
  getImplementationContractJob,
  getImplementationContractDiff,
  getImplementationContractExport,
  getImplementationContractVersion,
  getReader,
  getResearchMapJob,
  getResearchMapVersion,
  listDocuments,
  listImplementationContractVersions,
  resolveImplementationContractItem,
  reviewResearchNode,
  uploadDocument
} from './api'
import { ImplementationContract } from './ImplementationContract'
import {
  implementationContractReducer,
  initialImplementationContractState,
  pollImplementationContractJob
} from './implementationContractState'
import { Reader } from './Reader'
import { ResearchMap } from './ResearchMap'
import {
  initialResearchMapState,
  pollResearchMapJob,
  researchMapReducer
} from './researchMapState'
import type {
  DocumentRecord,
  ContractResolution,
  ContractResolutionStatus,
  ContractValue,
  ImplementationContract as ImplementationContractRecord,
  ImplementationContractJob,
  ImplementationContractDiff,
  ImplementationContractVersion,
  ReaderPayload,
  ResearchNodeReview,
  ReviewStatus
} from './types'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'
type Notice = { kind: 'status' | 'error'; message: string } | null
type WorkspaceSurface = 'map' | 'contract' | 'reader'
type ReaderReturnSurface = 'map' | 'contract' | null

export function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const processing = useDocumentProcessing(refreshDocuments)
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [reader, setReader] = useState<ReaderPayload | null>(null)
  const [activeDocument, setActiveDocument] = useState<DocumentRecord | null>(null)
  const [surface, setSurface] = useState<WorkspaceSurface>('map')
  const [readerReturnSurface, setReaderReturnSurface] =
    useState<ReaderReturnSurface>(null)
  const [mapReturnContractItemId, setMapReturnContractItemId] = useState<string | null>(null)
  const [contractVersions, setContractVersions] = useState<ImplementationContractVersion[]>([])
  const [contractDiff, setContractDiff] = useState<ImplementationContractDiff | null>(null)
  const [activationError, setActivationError] = useState<string | null>(null)
  const [mapState, dispatchMap] = useReducer(researchMapReducer, initialResearchMapState)
  const [contractState, dispatchContract] = useReducer(
    implementationContractReducer,
    initialImplementationContractState
  )
  const pollController = useRef<AbortController | null>(null)
  const reviewRequestSequence = useRef(0)
  const resolutionRequestSequence = useRef(0)
  const contractAuxRequestSequence = useRef(0)
  const activeDocumentId = useRef<string | null>(null)

  useEffect(
    () => () => {
      pollController.current?.abort()
      pollController.current = null
    },
    []
  )

  function abortPolling() {
    pollController.current?.abort()
    pollController.current = null
  }

  function resetContractAuxiliaryState() {
    contractAuxRequestSequence.current += 1
    setContractVersions([])
    setContractDiff(null)
    setActivationError(null)
  }

  function beginContractAuxRequest(documentId: string) {
    return {
      documentId,
      requestId: ++contractAuxRequestSequence.current
    }
  }

  function isCurrentContractAuxRequest(request: {
    documentId: string
    requestId: number
  }) {
    return (
      request.requestId === contractAuxRequestSequence.current &&
      request.documentId === activeDocumentId.current
    )
  }

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

  async function handleOpenReader(document: DocumentRecord) {
    setNotice({ kind: 'status', message: `Opening ${document.title}` })
    try {
      abortPolling()
      const nextReader = await getReader(document.id)
      activeDocumentId.current = document.id
      setActiveDocument(document)
      setReader(nextReader)
      dispatchMap({ type: 'resetWorkspace' })
      dispatchContract({ type: 'resetDocument', documentId: document.id })
      setReaderReturnSurface(null)
      setMapReturnContractItemId(null)
      resetContractAuxiliaryState()
      setSurface('reader')
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
    abortPolling()
    activeDocumentId.current = document.id
    setActiveDocument(document)
    setReader(null)
    setReaderReturnSurface(null)
    setMapReturnContractItemId(null)
    resetContractAuxiliaryState()
    setSurface('map')
    dispatchMap({ type: 'resetWorkspace' })
    dispatchContract({ type: 'resetDocument', documentId: document.id })
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
    abortPolling()
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
      if (controller.signal.aborted) return
      if (terminal?.status === 'completed') {
        const map = await getActiveResearchMap(activeDocument.id)
        if (controller.signal.aborted) return
        dispatchMap({ type: 'mapLoaded', map })
        await refreshDocuments()
      }
    } catch (error) {
      if (controller.signal.aborted) return
      console.error(error)
      dispatchMap({
        type: 'mapFailed',
        message: errorMessage(error, 'Could not generate the Research Map.')
      })
    } finally {
      if (pollController.current === controller) pollController.current = null
    }
  }

  async function handleMapEvidence(blockId: string) {
    if (!activeDocument || !mapState.map) return
    const documentId = activeDocument.id
    try {
      const payload = await getReader(documentId, mapState.map.source_content_hash)
      if (activeDocumentId.current !== documentId) return
      setReader(payload)
      dispatchMap({ type: 'openReader', blockId })
      setReaderReturnSurface('map')
      setSurface('reader')
    } catch (error) {
      if (activeDocumentId.current !== documentId) return
      console.error(error)
      dispatchMap({
        type: 'mapFailed',
        message: errorMessage(error, 'The cited Reader block could not be opened.')
      })
    }
  }

  async function handleContractEvidence(blockId: string) {
    if (!activeDocument || !contractState.contract) return
    const request = beginContractAuxRequest(activeDocument.id)
    try {
      const payload = await getReader(
        activeDocument.id,
        contractState.contract.source_content_hash
      )
      if (!isCurrentContractAuxRequest(request)) return
      setReader(payload)
      dispatchContract({ type: 'openReader', blockId })
      setReaderReturnSurface('contract')
      setSurface('reader')
    } catch (error) {
      if (!isCurrentContractAuxRequest(request)) return
      console.error(error)
      setNotice({
        kind: 'error',
        message: errorMessage(error, 'The cited Reader block could not be opened.')
      })
    }
  }

  async function handleContractMapNode(nodeId: string) {
    if (!activeDocument || !contractState.selectedItemId) return
    const request = beginContractAuxRequest(activeDocument.id)
    const returnItemId = contractState.selectedItemId
    try {
      if (!contractState.contract) return
      const map = await getResearchMapVersion(
        contractState.contract.research_map_version_id
      )
      if (!isCurrentContractAuxRequest(request)) return
      dispatchMap({ type: 'resetWorkspace' })
      dispatchMap({ type: 'mapLoaded', map })
      const linkedNodeExists = map.nodes.some((node) => node.id === nodeId)
      if (linkedNodeExists) {
        dispatchMap({ type: 'selectNode', nodeId })
        setNotice(null)
      } else {
        setNotice({
          kind: 'status',
          message: 'The linked Map node changed; Glyph selected the first available node.'
        })
      }
      dispatchMap({ type: 'openInspector' })
      setMapReturnContractItemId(returnItemId)
      setSurface('map')
    } catch (error) {
      if (!isCurrentContractAuxRequest(request)) return
      console.error(error)
      setNotice({
        kind: 'error',
        message: errorMessage(error, 'The linked Research Map node could not be opened.')
      })
    }
  }

  function handleReturnFromMapToContract() {
    const returnItemExists = contractState.contract?.items.some(
      (item) => item.id === mapReturnContractItemId
    )
    if (mapReturnContractItemId && returnItemExists) {
      dispatchContract({ type: 'selectItem', itemId: mapReturnContractItemId })
    } else if (mapReturnContractItemId && contractState.contract?.items.length) {
      dispatchContract({ type: 'selectItem', itemId: contractState.contract.items[0].id })
      setNotice({
        kind: 'status',
        message: 'The previous Contract item changed; Glyph selected the first available item.'
      })
    }
    dispatchContract({ type: 'openInspector' })
    setMapReturnContractItemId(null)
    setSurface('contract')
  }

  async function handleOpenContractHistory() {
    if (!activeDocument) return
    const request = beginContractAuxRequest(activeDocument.id)
    setActivationError(null)
    try {
      const versions = await listImplementationContractVersions(activeDocument.id)
      if (!isCurrentContractAuxRequest(request)) return
      setContractVersions(versions)
    } catch (error) {
      if (!isCurrentContractAuxRequest(request)) return
      setActivationError(errorMessage(error, 'Could not load Contract history.'))
    }
  }

  async function handleSelectContractVersion(versionId: string) {
    if (!activeDocument) return
    const request = beginContractAuxRequest(activeDocument.id)
    try {
      const contract = await getImplementationContractVersion(versionId)
      if (!isCurrentContractAuxRequest(request)) return
      dispatchContract({ type: 'contractLoaded', documentId: activeDocument.id, contract })
    } catch (error) {
      if (!isCurrentContractAuxRequest(request)) return
      setActivationError(errorMessage(error, 'Could not load that Contract version.'))
    }
  }

  async function handleCompareContractVersions(
    versionId: string,
    againstVersionId: string
  ) {
    if (!activeDocument) return
    const request = beginContractAuxRequest(activeDocument.id)
    try {
      const diff = await getImplementationContractDiff(versionId, againstVersionId)
      if (!isCurrentContractAuxRequest(request)) return
      setContractDiff(diff)
    } catch (error) {
      if (!isCurrentContractAuxRequest(request)) return
      setActivationError(errorMessage(error, 'Could not compare Contract versions.'))
    }
  }

  async function handleActivateContractVersion(versionId: string) {
    if (!activeDocument) return
    const request = beginContractAuxRequest(activeDocument.id)
    setActivationError(null)
    try {
      const contract = await activateImplementationContract(versionId)
      if (!isCurrentContractAuxRequest(request)) return
      dispatchContract({ type: 'contractLoaded', documentId: activeDocument.id, contract })
      const versions = await listImplementationContractVersions(activeDocument.id)
      if (!isCurrentContractAuxRequest(request)) return
      setContractVersions(versions)
      await refreshDocuments()
    } catch (error) {
      if (!isCurrentContractAuxRequest(request)) return
      setActivationError(errorMessage(error, 'Could not activate that Contract version.'))
    }
  }

  async function handleOpenContract(document: DocumentRecord) {
    abortPolling()
    activeDocumentId.current = document.id
    setActiveDocument(document)
    setReader(null)
    setReaderReturnSurface(null)
    setMapReturnContractItemId(null)
    resetContractAuxiliaryState()
    setSurface('contract')
    dispatchMap({ type: 'resetWorkspace' })
    dispatchContract({ type: 'resetDocument', documentId: document.id })
    dispatchContract({ type: 'contractLoading', documentId: document.id })
    try {
      const contract = await getActiveImplementationContract(document.id)
      dispatchContract({ type: 'contractLoaded', documentId: document.id, contract })
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        dispatchContract({ type: 'contractAbsent', documentId: document.id })
        return
      }
      console.error(error)
      dispatchContract({
        type: 'contractFailed',
        documentId: document.id,
        message: errorMessage(
          error,
          `Could not load the Implementation Contract for ${document.title}.`
        )
      })
    }
  }

  async function handleBuildContract(researchMapVersionId: string) {
    if (!activeDocument) return
    const document = activeDocument
    abortPolling()
    const controller = new AbortController()
    pollController.current = controller
    setReader(null)
    setReaderReturnSurface(null)
    setMapReturnContractItemId(null)
    resetContractAuxiliaryState()
    setSurface('contract')
    dispatchContract({ type: 'resetDocument', documentId: document.id })
    try {
      const queued = await enqueueImplementationContract(
        document.id,
        researchMapVersionId
      )
      if (controller.signal.aborted) return
      dispatchContract({ type: 'jobUpdated', documentId: document.id, job: queued })
      const terminal = await pollImplementationContractJob(queued.id, {
        fetchJob: getImplementationContractJob,
        onJob: (job) =>
          dispatchContract({ type: 'jobUpdated', documentId: document.id, job }),
        signal: controller.signal
      })
      if (controller.signal.aborted || terminal?.status !== 'completed') return
      dispatchContract({ type: 'contractLoading', documentId: document.id })
      const contract = await getActiveImplementationContract(document.id)
      if (controller.signal.aborted) return
      dispatchContract({ type: 'contractLoaded', documentId: document.id, contract })
      await refreshDocuments()
    } catch (error) {
      if (controller.signal.aborted) return
      console.error(error)
      dispatchContract({
        type: 'contractFailed',
        documentId: document.id,
        message: errorMessage(error, 'Could not generate the Implementation Contract.')
      })
    } finally {
      if (pollController.current === controller) pollController.current = null
    }
  }

  function handleReturnFromReader() {
    if (readerReturnSurface === 'map') {
      dispatchMap({ type: 'returnToMap' })
      setSurface('map')
    } else if (readerReturnSurface === 'contract') {
      dispatchContract({ type: 'returnToContract' })
      setSurface('contract')
    }
    setReaderReturnSurface(null)
  }

  async function handleContractResolution(
    status: ContractResolutionStatus,
    resolvedValue: ContractValue | null,
    reason: string | null
  ) {
    const contract = contractState.contract
    const item = contract?.items.find(
      (value) => value.id === contractState.selectedItemId
    )
    if (!contract || !item || contractState.pendingResolution) return
    const requestId = `contract-resolution-${++resolutionRequestSequence.current}`
    const optimisticResolution: ContractResolution = {
      id: `optimistic-${item.id}`,
      item_id: item.id,
      revision_number: (item.resolution?.revision_number ?? 0) + 1,
      supersedes_resolution_id: item.resolution?.id ?? null,
      status,
      resolved_value: resolvedValue,
      reason,
      based_on_contract_version_id: contract.id,
      based_on_item_signature: item.item_signature,
      request_id: requestId,
      resolved_at: new Date().toISOString()
    }
    dispatchContract({
      type: 'resolutionOptimistic',
      requestId,
      itemId: item.id,
      resolution: optimisticResolution
    })
    let saved: ContractResolution
    try {
      saved = await resolveImplementationContractItem(item.id, {
        request_id: requestId,
        status,
        based_on_item_signature: item.item_signature,
        resolved_value: resolvedValue,
        reason
      })
    } catch (error) {
      console.error(error)
      const message =
        error instanceof ApiError && error.status === 409
          ? `${error.message} Reload the Implementation Contract and decide again.`
          : errorMessage(error, 'The decision was not saved. Try again.')
      dispatchContract({ type: 'resolutionConflict', requestId, message })
      return
    }
    dispatchContract({
      type: 'resolutionSaved',
      requestId,
      itemId: item.id,
      resolution: saved
    })
    try {
      const refreshedContract = await getActiveImplementationContract(contract.document_id)
      if (activeDocumentId.current === contract.document_id) {
        dispatchContract({
          type: 'contractLoaded',
          documentId: contract.document_id,
          contract: refreshedContract
        })
      }
    } catch (error) {
      console.error(error)
      if (activeDocumentId.current === contract.document_id) {
        dispatchContract({
          type: 'contractFailed',
          documentId: contract.document_id,
          message:
            'Readiness could not be verified after saving the decision. Reload the Implementation Contract before implementation.'
        })
      }
    }
    await refreshDocuments()
  }

  async function handleReloadContract() {
    const document = activeDocument
    if (!document) return
    dispatchContract({ type: 'contractLoading', documentId: document.id })
    try {
      const contract = await getActiveImplementationContract(document.id)
      dispatchContract({ type: 'contractLoaded', documentId: document.id, contract })
    } catch (error) {
      console.error(error)
      dispatchContract({
        type: 'contractFailed',
        documentId: document.id,
        message: errorMessage(error, 'Could not reload the Implementation Contract.')
      })
    }
  }

  async function handleReview(
    status: ReviewStatus,
    correctedClaimText: string | null,
    reviewNote: string | null
  ) {
    const node = mapState.map?.nodes.find((item) => item.id === mapState.selectedNodeId)
    if (!node || mapState.pendingReview) return
    const requestId = `review-${++reviewRequestSequence.current}`
    const optimisticReview: ResearchNodeReview = {
      id: `optimistic-${node.id}`,
      status,
      corrected_claim_text: correctedClaimText,
      review_note: reviewNote,
      revision_number: (node.review?.revision_number ?? 0) + 1,
      supersedes_review_id: node.review?.id ?? null,
      reviewed_at: new Date().toISOString()
    }
    dispatchMap({ type: 'reviewOptimistic', requestId, nodeId: node.id, review: optimisticReview })
    try {
      const saved = await reviewResearchNode(node.id, {
        status,
        based_on_node_signature: node.node_signature,
        corrected_claim_text: correctedClaimText,
        review_note: reviewNote
      })
      dispatchMap({ type: 'reviewSaved', requestId, nodeId: node.id, review: saved })
      await refreshDocuments()
    } catch (error) {
      console.error(error)
      const message =
        error instanceof ApiError && error.status === 409
          ? `${error.message} Reload the Research Map and review it again.`
          : errorMessage(error, 'The review was not saved. Try again.')
      dispatchMap({ type: 'reviewConflict', requestId, message })
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
            <button type="button" className="icon-button" aria-expanded={settingsOpen} aria-controls="translation-settings" onClick={() => setSettingsOpen(!settingsOpen)}>
              {settingsOpen ? 'Close settings' : 'Translation settings'}
            </button>
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
            <button type="button" className="icon-button" onClick={() => { void refreshDocuments(); void processing.reload() }}>
              <RefreshCw aria-hidden="true" size={18} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {settingsOpen && <div id="translation-settings"><SettingsPage /></div>}

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

        {processing.loadError && <div className="error-line" role="alert">
          {processing.loadError}
          <button type="button" className="icon-button secondary" onClick={() => void processing.reload()}>Retry loading jobs</button>
        </div>}

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
                  {document.implementation_contract ? (
                    <LibraryContractSummary
                      document={document}
                      isActive={activeDocumentId.current === document.id}
                      loadStatus={contractState.loadStatus}
                      contract={contractState.contract}
                    />
                  ) : null}
                </div>
              </div>
              <div className="row-actions">
                <DocumentProcessing document={document} processing={processing} />
                <button
                  type="button"
                  className="icon-button secondary"
                  onClick={() => void handleOpenMap(document)}
                  aria-label={`Open Research Map for ${document.title}`}
                >
                  <FileSearch aria-hidden="true" size={16} />
                  <span>Research Map</span>
                </button>
                {canResumeContract(document) ? (
                  <button
                    type="button"
                    className="icon-button secondary"
                    onClick={() => void handleOpenContract(document)}
                    aria-label={`Resume Contract for ${document.title}`}
                  >
                    <FileSearch aria-hidden="true" size={16} />
                    <span>Resume Contract</span>
                  </button>
                ) : null}
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

      {activeDocument && surface === 'map' ? (
        mapState.loadStatus === 'loading' ? (
          <section className="workspace-loading" aria-label="Loading Research Map">
            <Loader2 aria-hidden="true" size={20} /> Loading Research Map
          </section>
        ) : (
          <>
            {mapReturnContractItemId ? (
              <button
                type="button"
                className="text-button workspace-return"
                onClick={handleReturnFromMapToContract}
                aria-label="Return to Implementation Contract"
              >
                Return to Implementation Contract
              </button>
            ) : null}
            <ResearchMap
              map={mapState.map}
              selectedNodeId={mapState.selectedNodeId}
              guidedStep={mapState.guidedStep}
              inspectorOpen={mapState.inspectorOpen}
              notice={mapState.notice}
              job={mapState.job}
              reviewPending={mapState.pendingReview !== null}
              onSelectNode={(nodeId) => dispatchMap({ type: 'selectNode', nodeId })}
              onOpenInspector={() => dispatchMap({ type: 'openInspector' })}
              onCloseInspector={() => dispatchMap({ type: 'closeInspector' })}
              onGuidedNext={() => dispatchMap({ type: 'guidedNext' })}
              onGuidedPrevious={() => dispatchMap({ type: 'guidedPrevious' })}
              onOpenReader={(blockId) => void handleMapEvidence(blockId)}
              onReview={(status, corrected, note) => void handleReview(status, corrected, note)}
              onGenerate={() => void handleGenerateMap()}
              onBuildContract={(researchMapVersionId) =>
                void handleBuildContract(researchMapVersionId)
              }
            />
          </>
        )
      ) : null}
      {activeDocument && surface === 'contract' ? (
        contractState.loadStatus === 'ready' && contractState.contract ? (
          <ImplementationContract
            key={activeDocument.id}
            contract={contractState.contract}
            selectedItemId={contractState.selectedItemId}
            guidedStep={contractState.guidedStep}
            inspectorOpen={contractState.inspectorOpen}
            notice={contractState.notice}
            resolutionPending={contractState.pendingResolution !== null}
            onSelectItem={(itemId) => dispatchContract({ type: 'selectItem', itemId })}
            onOpenInspector={() => dispatchContract({ type: 'openInspector' })}
            onCloseInspector={() => dispatchContract({ type: 'closeInspector' })}
            onGuidedNext={() => dispatchContract({ type: 'guidedNext' })}
            onGuidedPrevious={() => dispatchContract({ type: 'guidedPrevious' })}
            onOpenReader={(blockId) => void handleContractEvidence(blockId)}
            onResolve={(status, value, reason) =>
              void handleContractResolution(status, value, reason)
            }
            onRemainBlocked={() => dispatchContract({ type: 'closeInspector' })}
            versions={contractVersions}
            diff={contractDiff}
            activationError={activationError}
            onOpenHistory={() => void handleOpenContractHistory()}
            onSelectVersion={(versionId) => void handleSelectContractVersion(versionId)}
            onCompareVersions={(versionId, againstVersionId) =>
              void handleCompareContractVersions(versionId, againstVersionId)
            }
            onActivateVersion={(versionId) => void handleActivateContractVersion(versionId)}
            onExport={(format, language) => {
              const contract = contractState.contract
              if (!contract) return Promise.reject(new Error('Contract export is unavailable.'))
              return getImplementationContractExport(contract.id, format, language)
            }}
            onOpenMapNode={(nodeId) => void handleContractMapNode(nodeId)}
          />
        ) : (
          <ContractWorkspaceState
            loadStatus={contractState.loadStatus}
            job={contractState.job}
            notice={contractState.notice}
            onRetry={() => void handleReloadContract()}
          />
        )
      ) : null}
      {reader && surface === 'reader' ? (
        <Reader
          payload={reader}
          focusBlockId={
            readerReturnSurface === 'contract'
              ? contractState.readerFocusBlockId
              : mapState.readerFocusBlockId || null
          }
          citingNodes={
            readerReturnSurface === 'contract' && contractState.readerFocusBlockId
              ? (contractState.contract?.items ?? [])
                  .filter((item) =>
                    item.evidence.some(
                      (evidence) => evidence.block_id === contractState.readerFocusBlockId
                    )
                  )
                  .map((item) => ({ id: item.id, title: item.item_type.replaceAll('_', ' ') }))
              : mapState.readerFocusBlockId
              ? (mapState.map?.nodes ?? [])
                  .filter((node) =>
                    node.evidence.some(
                      (evidence) => evidence.block_id === mapState.readerFocusBlockId
                    )
                  )
                  .map((node) => ({ id: node.id, title: node.title }))
              : []
          }
          onReturn={readerReturnSurface ? handleReturnFromReader : undefined}
          returnLabel={
            readerReturnSurface === 'contract'
              ? 'Implementation Contract'
              : 'Research Map'
          }
          citationSource={
            readerReturnSurface === 'contract'
              ? 'Contract'
              : readerReturnSurface === 'map'
                ? 'Map'
                : undefined
          }
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
      return 'Not processed'
    case 'uploaded':
      return 'Uploaded · not processed'
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

function canResumeContract(document: DocumentRecord): boolean {
  const summary = document.implementation_contract
  return Boolean(
    summary?.is_current &&
      (summary.generation_status === 'complete' ||
        summary.generation_status === 'partial')
  )
}

function contractReadinessLabel(
  readiness: NonNullable<DocumentRecord['implementation_contract']>['readiness']
): string {
  switch (readiness) {
    case 'blocked':
      return 'Blocked'
    case 'review_needed':
      return 'Review needed'
    case 'implementation_ready':
      return 'Implementation ready'
  }
}

function LibraryContractSummary({
  document,
  isActive,
  loadStatus,
  contract
}: {
  document: DocumentRecord
  isActive: boolean
  loadStatus: 'idle' | 'loading' | 'absent' | 'ready' | 'error'
  contract: ImplementationContractRecord | null
}) {
  const listed = document.implementation_contract
  if (!listed) return null
  if (isActive && loadStatus !== 'ready') {
    return (
      <div
        className="library-map-summary"
        aria-label={`Implementation Contract status for ${document.title}`}
      >
        <span>Readiness unverified · blocker count unverified</span>
        <span>Review progress unverified</span>
        <span>Contract refresh required</span>
      </div>
    )
  }
  const authoritative =
    isActive && contract?.document_id === document.id && contract.is_active
      ? contract
      : null
  const blockerCount = authoritative
    ? authoritative.issues.filter((issue) => issue.severity === 'error').length
    : listed.blocker_count
  const reviewedCount = authoritative
    ? authoritative.items.filter((item) => item.resolution !== null).length
    : listed.reviewed_count
  const totalReviewableCount = authoritative
    ? authoritative.items.length
    : listed.total_reviewable_count
  const readiness = authoritative?.readiness ?? listed.readiness
  const isStale = authoritative?.is_stale ?? listed.is_stale
  const generationStatus = authoritative?.status ?? listed.generation_status
  return (
    <div
      className="library-map-summary"
      aria-label={`Implementation Contract status for ${document.title}`}
    >
      <span>
        {contractReadinessLabel(readiness)} · {blockerCount} blocker
        {blockerCount === 1 ? '' : 's'}
      </span>
      <span>
        {reviewedCount} / {totalReviewableCount} reviewed
      </span>
      <span>
        {isStale ? 'Stale' : 'Current'} · {generationStatus}
      </span>
    </div>
  )
}

function ContractWorkspaceState({
  loadStatus,
  job,
  notice,
  onRetry
}: {
  loadStatus: 'idle' | 'loading' | 'absent' | 'ready' | 'error'
  job: ImplementationContractJob | null
  notice: Notice
  onRetry: () => void
}) {
  const generationActive = job?.status === 'queued' || job?.status === 'running'
  return (
    <section
      className="research-map-empty"
      aria-label="Implementation Contract workspace"
    >
      <FileSearch aria-hidden="true" size={28} />
      <p className="kicker">Implementation Contract</p>
      {generationActive && job ? (
        <div className="map-job-progress" role="status">
          <div>
            <span>{job.stage}</span>
            <strong>{Math.round(job.progress)}%</strong>
          </div>
          <progress value={job.progress} max="100">
            {job.progress}%
          </progress>
        </div>
      ) : null}
      {loadStatus === 'loading' ? (
        <p className="status-line">
          <Loader2 aria-hidden="true" size={16} /> Loading Implementation Contract
        </p>
      ) : null}
      {loadStatus === 'ready' ? <h2>Contract ready for review</h2> : null}
      {loadStatus === 'absent' ? <h2>No Implementation Contract yet</h2> : null}
      {notice ? (
        <p
          className={notice.kind === 'error' ? 'error-line' : 'status-line'}
          role={notice.kind === 'error' ? 'alert' : 'status'}
        >
          {notice.message}
        </p>
      ) : null}
      {loadStatus === 'error' ? (
        <button type="button" onClick={onRetry}>
          Reload Implementation Contract
        </button>
      ) : null}
    </section>
  )
}
