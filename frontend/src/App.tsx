import { BookOpen, FileUp, Loader2, Play, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'

import { getReader, listDocuments, processDocument, uploadDocument } from './api'
import { Reader } from './Reader'
import type { DocumentRecord, ReaderPayload } from './types'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

export function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [activeMessage, setActiveMessage] = useState('')
  const [reader, setReader] = useState<ReaderPayload | null>(null)

  async function refreshDocuments() {
    setLoadState('loading')
    try {
      setDocuments(await listDocuments())
      setLoadState('ready')
      setActiveMessage('')
    } catch (error) {
      console.error(error)
      setLoadState('error')
      setActiveMessage('Could not load documents.')
    }
  }

  useEffect(() => {
    void refreshDocuments()
  }, [])

  async function handleUpload(file: File | undefined) {
    if (!file) return
    setActiveMessage(`Uploading ${file.name}`)
    try {
      await uploadDocument(file)
      await refreshDocuments()
    } catch (error) {
      console.error(error)
      setActiveMessage('Upload failed.')
    }
  }

  async function handleProcess(document: DocumentRecord) {
    setActiveMessage(`Processing ${document.title}`)
    try {
      await processDocument(document.id)
      await refreshDocuments()
      setActiveMessage(`Processed ${document.title}`)
    } catch (error) {
      console.error(error)
      setActiveMessage(`Processing failed for ${document.title}`)
    }
  }

  async function handleOpen(document: DocumentRecord) {
    setActiveMessage(`Opening ${document.title}`)
    try {
      setReader(await getReader(document.id))
      setActiveMessage('')
    } catch (error) {
      console.error(error)
      setActiveMessage(`Reader is not ready for ${document.title}`)
    }
  }

  return (
    <main className="app-shell">
      <section
        className={reader ? 'library-panel library-panel-compact' : 'library-panel'}
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

        {activeMessage ? <p className="status-line">{activeMessage}</p> : null}
        {loadState === 'loading' ? (
          <p className="status-line">
            <Loader2 aria-hidden="true" size={16} /> Loading documents
          </p>
        ) : null}
        {loadState === 'error' ? <p className="error-line">Could not load documents.</p> : null}

        <div className="document-list" aria-label="Documents">
          {documents.map((document) => (
            <article className="document-row" key={document.id}>
              <div className="document-main">
                <BookOpen aria-hidden="true" size={18} />
                <div>
                  <h2>{document.title}</h2>
                  <p>
                    {document.file_type.toUpperCase()} · {document.status}
                  </p>
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
                  onClick={() => void handleOpen(document)}
                  aria-label={`Open ${document.title}`}
                >
                  <BookOpen aria-hidden="true" size={16} />
                  <span>Open</span>
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {reader ? <Reader payload={reader} /> : null}
    </main>
  )
}
