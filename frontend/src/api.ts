import type {
  DocumentRecord,
  DocumentStatus,
  EvidenceLocatorType,
  EvidenceQuality,
  EvidenceRelation,
  ProcessingJob,
  ReaderPayload,
  ResearchMap,
  ResearchMapDiff,
  ResearchMapDiffClassification,
  ResearchMapJob,
  ResearchMapJobStatus,
  ResearchMapStatus,
  ResearchNodeReviewInput,
  ResearchNodeReviewRecord,
  ResearchNodeType,
  ResearchProvenance,
  ReviewStatus,
  ResearchMapVersion
} from './types'

const apiBase = ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

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

export async function enqueueResearchMap(documentId: string): Promise<ResearchMapJob> {
  return fetchJson(`/api/documents/${documentId}/research-map`, isResearchMapJob, {
    method: 'POST'
  })
}

export async function getResearchMapJob(jobId: string): Promise<ResearchMapJob> {
  return fetchJson(`/api/research-map-jobs/${jobId}`, isResearchMapJob)
}

export async function getActiveResearchMap(documentId: string): Promise<ResearchMap> {
  return fetchJson(`/api/documents/${documentId}/research-map`, isResearchMap)
}

export async function getResearchMapVersion(versionId: string): Promise<ResearchMap> {
  return fetchJson(`/api/research-maps/${versionId}`, isResearchMap)
}

export async function listResearchMapVersions(documentId: string): Promise<ResearchMapVersion[]> {
  return fetchJson(
    `/api/documents/${documentId}/research-map/versions`,
    isResearchMapVersionArray
  )
}

export async function reviewResearchNode(
  nodeId: string,
  input: ResearchNodeReviewInput
): Promise<ResearchNodeReviewRecord> {
  return fetchJson(`/api/research-nodes/${nodeId}/review`, isResearchNodeReviewRecord, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(input)
  })
}

export async function activateResearchMap(versionId: string): Promise<ResearchMap> {
  return fetchJson(`/api/research-maps/${versionId}/activate`, isResearchMap, {
    method: 'POST'
  })
}

export async function getResearchMapDiff(
  versionId: string,
  againstVersionId: string
): Promise<ResearchMapDiff> {
  return fetchJson(
    `/api/research-maps/${versionId}/diff?against=${encodeURIComponent(againstVersionId)}`,
    isResearchMapDiff
  )
}

async function fetchJson<T>(
  path: string,
  validate: (value: unknown) => value is T,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init)
  if (!response.ok) {
    throw await responseError(response)
  }
  const payload: unknown = await response.json()
  if (!validate(payload)) {
    throw new Error('Unexpected API response shape')
  }
  return payload
}

async function responseError(response: Response): Promise<ApiError> {
  const fallback = `Request failed with ${response.status}`
  if (!response.headers.get('content-type')?.includes('application/json')) {
    return new ApiError(response.status, fallback)
  }

  try {
    const payload: unknown = await response.json()
    if (isRecord(payload) && isString(payload.detail)) {
      return new ApiError(response.status, payload.detail)
    }
  } catch {
    // A malformed error body is not useful to callers; preserve the HTTP status fallback.
  }
  return new ApiError(response.status, fallback)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isInteger(value: unknown): value is number {
  return isNumber(value) && Number.isInteger(value)
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

function isIsoDate(value: unknown): value is string {
  return isString(value) && !Number.isNaN(Date.parse(value))
}

function isNullableIsoDate(value: unknown): value is string | null {
  return value === null || isIsoDate(value)
}

function isHexHash(value: unknown): value is string {
  return isString(value) && /^[0-9a-f]{64}$/.test(value)
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isDocumentStatus(value: unknown): value is DocumentStatus {
  return (
    value === 'discovered' ||
    value === 'uploaded' ||
    value === 'processing' ||
    value === 'completed' ||
    value === 'failed' ||
    value === 'stale' ||
    value === 'missing'
  )
}

function isDocument(value: unknown): value is DocumentRecord {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.title) &&
    isString(value.file_type) &&
    isDocumentStatus(value.status) &&
    (!('research_map' in value) ||
      value.research_map === null ||
      isResearchMapSummary(value.research_map))
  )
}

function isResearchMapSummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.version_id) &&
    isOneOf(value.status, mapStatuses) &&
    isBoolean(value.is_current) &&
    isBoolean(value.is_stale) &&
    isInteger(value.reviewed_core_nodes) &&
    value.reviewed_core_nodes >= 0 &&
    isInteger(value.reviewable_core_nodes) &&
    value.reviewable_core_nodes >= value.reviewed_core_nodes &&
    isInteger(value.issue_count) &&
    value.issue_count >= 0
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

const researchNodeTypes: readonly ResearchNodeType[] = [
  'author_claim',
  'economic_mechanism',
  'hypothesis',
  'data_and_sample',
  'data_source',
  'sample_filter',
  'signal_definition',
  'variable_definition',
  'portfolio_construction',
  'rebalancing_rule',
  'empirical_method',
  'benchmark_model',
  'identification_strategy',
  'primary_result',
  'statistical_evidence',
  'economic_magnitude',
  'turnover',
  'transaction_cost',
  'robustness_test',
  'subsample_result',
  'alternative_explanation',
  'implementation_constraint',
  'limitations',
  'unanswered_question'
]
const provenances: readonly ResearchProvenance[] = [
  'author_explicit',
  'ai_synthesis',
  'human_created'
]
const evidenceQualities: readonly EvidenceQuality[] = [
  'direct',
  'synthesized',
  'insufficient',
  'conflicted',
  'not_reported'
]
const evidenceRelations: readonly EvidenceRelation[] = [
  'supports',
  'qualifies',
  'contradicts',
  'context'
]
const locatorTypes: readonly EvidenceLocatorType[] = [
  'text_span',
  'equation',
  'table',
  'figure',
  'caption'
]
const reviewStatuses: readonly ReviewStatus[] = ['confirmed', 'questioned', 'corrected']
const mapStatuses: readonly ResearchMapStatus[] = ['building', 'complete', 'partial', 'failed']
const jobStatuses: readonly ResearchMapJobStatus[] = ['queued', 'running', 'completed', 'failed']
const diffClassifications: readonly ResearchMapDiffClassification[] = [
  'unchanged',
  'claim_changed',
  'evidence_changed',
  'added',
  'removed'
]

function isOneOf<T extends string>(value: unknown, allowed: readonly T[]): value is T {
  return typeof value === 'string' && allowed.some((item) => item === value)
}

function isResearchMapJob(value: unknown): value is ResearchMapJob {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.document_id) &&
    isNullableString(value.map_version_id) &&
    isOneOf(value.status, jobStatuses) &&
    isString(value.stage) &&
    isNumber(value.progress) &&
    value.progress >= 0 &&
    value.progress <= 100 &&
    isNullableString(value.error_message) &&
    isInteger(value.attempt_count) &&
    value.attempt_count >= 0 &&
    isIsoDate(value.created_at) &&
    isIsoDate(value.updated_at)
  )
}

function isResearchEvidence(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.block_id) &&
    isOneOf(value.locator_type, locatorTypes) &&
    isString(value.quote_text) &&
    value.quote_text.length > 0 &&
    isInteger(value.quote_start) &&
    value.quote_start >= 0 &&
    isInteger(value.quote_end) &&
    value.quote_end > value.quote_start &&
    isHexHash(value.source_quote_hash) &&
    isOneOf(value.relation, evidenceRelations) &&
    isNullableString(value.source_label) &&
    isInteger(value.page_number) &&
    value.page_number > 0 &&
    isString(value.block_type) &&
    isString(value.translated_text)
  )
}

function isResearchMapIssue(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isNullableString(value.node_id) &&
    isString(value.code) &&
    isOneOf(value.severity, ['info', 'warning', 'error']) &&
    isString(value.message)
  )
}

function isResearchNodeReview(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isOneOf(value.status, reviewStatuses) &&
    isNullableString(value.corrected_claim_text) &&
    isNullableString(value.review_note) &&
    isInteger(value.revision_number) &&
    value.revision_number > 0 &&
    isNullableString(value.supersedes_review_id) &&
    isIsoDate(value.reviewed_at)
  )
}

function isResearchNodeReviewRecord(value: unknown): value is ResearchNodeReviewRecord {
  return (
    isResearchNodeReview(value) &&
    isRecord(value) &&
    isString(value.node_id) &&
    isString(value.based_on_map_version_id) &&
    isHexHash(value.based_on_node_signature)
  )
}

function isResearchNode(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isNullableString(value.parent_node_id) &&
    isString(value.node_key) &&
    isOneOf(value.node_type, researchNodeTypes) &&
    isString(value.title) &&
    isString(value.claim_text) &&
    isString(value.effective_claim_text) &&
    isString(value.explanation) &&
    isOneOf(value.provenance, provenances) &&
    isOneOf(value.evidence_quality, evidenceQualities) &&
    isInteger(value.display_order) &&
    value.display_order >= 0 &&
    isHexHash(value.node_signature) &&
    Array.isArray(value.evidence) &&
    value.evidence.every(isResearchEvidence) &&
    Array.isArray(value.issues) &&
    value.issues.every(isResearchMapIssue) &&
    (value.review === null || isResearchNodeReview(value.review))
  )
}

function isResearchMapBase(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.document_id) &&
    isNullableString(value.previous_version_id) &&
    isHexHash(value.source_content_hash) &&
    isString(value.schema_version) &&
    isString(value.provider) &&
    isNullableString(value.model_name) &&
    isOneOf(value.status, mapStatuses) &&
    isBoolean(value.is_active) &&
    isBoolean(value.is_current) &&
    isBoolean(value.is_stale) &&
    isIsoDate(value.created_at) &&
    isNullableIsoDate(value.completed_at)
  )
}

function isResearchMap(value: unknown): value is ResearchMap {
  return (
    isResearchMapBase(value) &&
    isRecord(value) &&
    isInteger(value.reviewed_core_nodes) &&
    value.reviewed_core_nodes >= 0 &&
    isInteger(value.reviewable_core_nodes) &&
    value.reviewable_core_nodes >= value.reviewed_core_nodes &&
    Array.isArray(value.nodes) &&
    value.nodes.every(isResearchNode) &&
    Array.isArray(value.issues) &&
    value.issues.every(isResearchMapIssue)
  )
}

function isResearchMapVersion(value: unknown): value is ResearchMapVersion {
  return isResearchMapBase(value)
}

function isResearchMapVersionArray(value: unknown): value is ResearchMapVersion[] {
  return Array.isArray(value) && value.every(isResearchMapVersion)
}

function isResearchMapDiff(value: unknown): value is ResearchMapDiff {
  return (
    isRecord(value) &&
    isString(value.version_id) &&
    isString(value.against_version_id) &&
    Array.isArray(value.nodes) &&
    value.nodes.every(
      (node) =>
        isRecord(node) &&
        isString(node.node_key) &&
        isOneOf(node.classification, diffClassifications) &&
        isNullableString(node.version_node_id) &&
        isNullableString(node.against_node_id)
    )
  )
}
