import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelProcessingJob, getProcessingPreflight, listProcessingJobs, processDocument } from './api'
import type { DocumentRecord, ProcessingJob, ProcessingPreflight } from './types'

function isActive(job: ProcessingJob | undefined) {
  return job?.status === 'queued' || job?.status === 'running'
}
function message(error: unknown) {
  return error instanceof Error ? error.message : 'Could not update processing. Please try again.'
}

export function useDocumentProcessing(onChanged: () => Promise<void>, pollInterval = 1500) {
  const [jobs, setJobs] = useState<Record<string, ProcessingJob>>({})
  const [checks, setChecks] = useState<Record<string, ProcessingPreflight>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const mounted = useRef(false)
  const jobsRef = useRef(jobs)
  const busyRef = useRef(new Set<string>())
  const mutation = useRef(0)
  const request = useRef(0)
  const onChangedRef = useRef(onChanged)
  onChangedRef.current = onChanged

  const refreshDocuments = useCallback(() => {
    void onChangedRef.current().catch(() => {
      if (mounted.current) setLoadError('Processing updated, but the document list could not refresh. Retry loading jobs.')
    })
  }, [])

  const publish = useCallback((next: Record<string, ProcessingJob>) => {
    const finished = Object.values(next).some(job =>
      isActive(jobsRef.current[job.document_id]) && !isActive(job))
    jobsRef.current = next
    setJobs(next)
    if (finished) refreshDocuments()
  }, [refreshDocuments])

  const reload = useCallback(async () => {
    const sequence = ++request.current
    const revision = mutation.current
    try {
      const values = await listProcessingJobs()
      if (!mounted.current || sequence !== request.current || revision !== mutation.current) return
      const next = Object.fromEntries(values.map(job => [job.document_id, job]))
      publish(next)
      setLoadError(null)
    } catch (error) {
      if (mounted.current && sequence === request.current && revision === mutation.current) {
        setLoadError(message(error))
      }
    } finally {
      if (mounted.current && sequence === request.current) setLoading(false)
    }
  }, [publish])

  useEffect(() => {
    mounted.current = true
    void reload()
    return () => { mounted.current = false; request.current += 1 }
  }, [reload])

  const active = Object.values(jobs).some(isActive)
  useEffect(() => {
    if (!active) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      await reload()
      if (!stopped && Object.values(jobsRef.current).some(isActive)) {
        timer = setTimeout(() => void poll(), pollInterval)
      }
    }
    timer = setTimeout(() => void poll(), pollInterval)
    return () => { stopped = true; clearTimeout(timer) }
  }, [active, reload, pollInterval])

  async function start(documentId: string) {
    if (busyRef.current.has(documentId) || isActive(jobsRef.current[documentId]) || loading || loadError) return
    busyRef.current.add(documentId)
    mutation.current += 1
    setBusy(value => ({ ...value, [documentId]: true }))
    setErrors(value => ({ ...value, [documentId]: '' }))
    try {
      const check = await getProcessingPreflight(documentId)
      if (!mounted.current) return
      setChecks(value => ({ ...value, [documentId]: check }))
      if (!check.ready) return
      const job = await processDocument(documentId)
      if (!mounted.current) return
      mutation.current += 1
      publish({ ...jobsRef.current, [documentId]: job })
      if (!isActive(job)) refreshDocuments()
    } catch (error) {
      if (mounted.current) setErrors(value => ({ ...value, [documentId]: message(error) }))
    } finally {
      busyRef.current.delete(documentId)
      if (mounted.current) setBusy(value => ({ ...value, [documentId]: false }))
    }
  }

  async function cancel(documentId: string) {
    const job = jobsRef.current[documentId]
    if (!job || !isActive(job) || job.cancel_requested || busyRef.current.has(documentId)) return
    busyRef.current.add(documentId)
    mutation.current += 1
    setBusy(value => ({ ...value, [documentId]: true }))
    setErrors(value => ({ ...value, [documentId]: '' }))
    try {
      const updated = await cancelProcessingJob(job.id)
      if (!mounted.current) return
      mutation.current += 1
      publish({ ...jobsRef.current, [documentId]: updated })
    } catch (error) {
      if (mounted.current) setErrors(value => ({ ...value, [documentId]: message(error) }))
    } finally {
      busyRef.current.delete(documentId)
      if (mounted.current) setBusy(value => ({ ...value, [documentId]: false }))
    }
  }

  return { jobs, checks, errors, busy, loading, loadError, reload, start, cancel }
}

type Processing = ReturnType<typeof useDocumentProcessing>

export function DocumentProcessing({ document, processing }: {
  document: DocumentRecord
  processing: Processing
}) {
  const job = processing.jobs[document.id]
  const busy = processing.busy[document.id]
  const error = processing.errors[document.id]
  const check = processing.checks[document.id]
  const active = isActive(job)
  const retry = job && ['failed', 'cancelled', 'interrupted'].includes(job.status)
  return <div className="document-processing">
    <div className="processing-actions">
      <button type="button" className="icon-button"
        disabled={processing.loading || Boolean(processing.loadError) || busy || active}
        aria-label={retry ? `Retry processing ${document.title}` : `Process ${document.title}`}
        onClick={() => void processing.start(document.id)}>
        {busy && !active ? 'Checking…' : retry ? 'Retry processing' : 'Process'}
      </button>
      {active && <button type="button" className="icon-button secondary"
        disabled={busy || job?.cancel_requested}
        aria-label={`Cancel processing ${document.title}`}
        onClick={() => void processing.cancel(document.id)}>
        {job?.cancel_requested ? 'Cancelling…' : 'Cancel'}
      </button>}
    </div>
    {error && <p className="error-line" role="alert">{error}</p>}
    {check?.issues.map(issue => <p key={issue.code}
      role={issue.severity === 'error' ? 'alert' : undefined}
      className={issue.severity === 'error' ? 'error-line' : 'processing-warning'}>{issue.message}</p>)}
    {check && !check.ready && check.issues.length === 0 && <p role="alert">This document is not ready to process. Check the source and provider settings.</p>}
    {active && job && <div className="processing-progress">
      <p role="status">{job.status === 'queued' ? 'Queued' : stageLabel(job.stage)}</p>
      <progress aria-label={`Processing ${document.title}`} value={job.progress} max={100} />
      {job.total_blocks != null && job.completed_blocks != null &&
        <p>{job.completed_blocks} / {job.total_blocks} blocks</p>}
      {job.cancel_requested && <p>Cancellation requested. The current external call may finish before processing stops.</p>}
    </div>}
    {!active && job && <p role={job.status === 'failed' || job.status === 'interrupted' ? 'alert' : 'status'}
      className={job.status === 'failed' || job.status === 'interrupted' ? 'error-line' : 'processing-result'}>
      {job.status === 'completed' ? `Processed ${document.title}` : job.error_message ??
        (job.status === 'cancelled' ? 'Processing cancelled. You can retry with your current settings.' : 'Processing stopped. You can retry with your current settings.')}
    </p>}
  </div>
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    preflight: 'Checking document', ocr: 'Extracting text', ai_parse: 'Translating',
    translation: 'Translating', translate: 'Translating', persist: 'Saving reader'
  }
  return labels[stage] ?? stage.replaceAll('_', ' ')
}
