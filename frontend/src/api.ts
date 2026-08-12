import type { DocumentRecord, ProcessingJob, ReaderPayload } from './types'

const apiBase = ''

export async function listDocuments(): Promise<DocumentRecord[]> {
  return fetchJson('/api/documents', isDocumentArray)
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const form = new FormData()
  form.append('file', file)
  return fetchJson('/api/documents/upload', isDocument, {
    method: 'POST',
    body: form
  })
}

export async function processDocument(documentId: string): Promise<ProcessingJob> {
  return fetchJson(`/api/documents/${documentId}/process`, isProcessingJob, {
    method: 'POST'
  })
}

export async function getReader(documentId: string): Promise<ReaderPayload> {
  return fetchJson(`/api/documents/${documentId}/reader`, isReaderPayload)
}

async function fetchJson<T>(
  path: string,
  validate: (value: unknown) => value is T,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init)
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`)
  }
  const payload: unknown = await response.json()
  if (!validate(payload)) {
    throw new Error('Unexpected API response shape')
  }
  return payload
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number'
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isDocument(value: unknown): value is DocumentRecord {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.title) &&
    isString(value.file_type) &&
    isString(value.status)
  )
}

function isDocumentArray(value: unknown): value is DocumentRecord[] {
  return Array.isArray(value) && value.every(isDocument)
}

function isProcessingJob(value: unknown): value is ProcessingJob {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.document_id) &&
    isString(value.status) &&
    isString(value.stage) &&
    isNumber(value.progress) &&
    isNullableString(value.error_message)
  )
}

function isReaderBlock(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isNumber(value.order_index) &&
    isNumber(value.page_number) &&
    isString(value.block_type) &&
    isString(value.source_text) &&
    isString(value.translated_text) &&
    isNullableString(value.formula_latex) &&
    isString(value.page_image_url) &&
    isNullableString(value.section_path) &&
    isNumber(value.confidence)
  )
}

function isReaderSection(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.title) &&
    isString(value.path) &&
    isNumber(value.order_index) &&
    isString(value.summary) &&
    isNumber(value.progress)
  )
}

function isReaderPayload(value: unknown): value is ReaderPayload {
  return (
    isRecord(value) &&
    isDocument(value.document) &&
    Array.isArray(value.blocks) &&
    value.blocks.every(isReaderBlock) &&
    Array.isArray(value.sections) &&
    value.sections.every(isReaderSection) &&
    isString(value.summary)
  )
}
