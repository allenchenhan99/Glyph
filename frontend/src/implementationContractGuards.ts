import type {
  ContractDiffClassification,
  ContractGenerationStatus,
  ContractItemType,
  ContractOrigin,
  ContractPeriodUnit,
  ContractReadiness,
  ContractResolution,
  ContractResolutionStatus,
  ContractRuleOperator,
  ContractSection,
  ContractValue,
  EvidenceLocatorType,
  EvidenceRelation,
  ImplementationContract,
  ImplementationContractDiff,
  ImplementationContractJob,
  ImplementationContractJobStatus,
  ImplementationContractSummary,
  ImplementationContractVersion
} from './types'

const contractSections: readonly ContractSection[] = [
  'thesis',
  'data_requirements',
  'universe_and_sample',
  'signal_and_timing',
  'portfolio_construction',
  'evaluation',
  'frictions_and_risks',
  'open_decisions'
]
const contractItemTypes: readonly ContractItemType[] = [
  'required_dataset',
  'required_field',
  'data_frequency',
  'availability_lag',
  'sample_period',
  'universe_filter',
  'sample_filter',
  'signal_formula',
  'signal_direction',
  'formation_date',
  'lookback_window',
  'weighting_rule',
  'rebalance_frequency',
  'holding_period',
  'long_short_definition',
  'benchmark_model',
  'evaluation_metric',
  'statistical_test',
  'transaction_cost',
  'turnover_assumption',
  'survivorship_risk',
  'lookahead_risk',
  'implementation_constraint'
]
const contractOrigins: readonly ContractOrigin[] = [
  'author_explicit',
  'derived',
  'human_decision',
  'missing'
]
const generationStatuses: readonly ContractGenerationStatus[] = [
  'building',
  'complete',
  'partial',
  'failed'
]
const readinessStates: readonly ContractReadiness[] = [
  'blocked',
  'review_needed',
  'implementation_ready'
]
const resolutionStatuses: readonly ContractResolutionStatus[] = [
  'confirmed',
  'corrected',
  'decided',
  'questioned',
  'not_applicable'
]
const jobStatuses: readonly ImplementationContractJobStatus[] = [
  'queued',
  'running',
  'completed',
  'failed'
]
const diffClassifications: readonly ContractDiffClassification[] = [
  'unchanged',
  'type_changed',
  'value_changed',
  'origin_changed',
  'evidence_changed',
  'added',
  'removed'
]
const ruleOperators: readonly ContractRuleOperator[] = [
  'include',
  'exclude',
  'rank',
  'threshold'
]
const periodUnits: readonly ContractPeriodUnit[] = [
  'business_day',
  'day',
  'week',
  'month',
  'quarter',
  'year'
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

export function isImplementationContractSummary(
  value: unknown
): value is ImplementationContractSummary {
  return (
    isExactRecord(value, [
      'version_id',
      'generation_status',
      'readiness',
      'is_current',
      'is_stale',
      'blocker_count',
      'reviewed_count',
      'total_reviewable_count'
    ]) &&
    isString(value.version_id) &&
    isOneOf(value.generation_status, generationStatuses) &&
    isOneOf(value.readiness, readinessStates) &&
    isBoolean(value.is_current) &&
    isBoolean(value.is_stale) &&
    isNonNegativeInteger(value.blocker_count) &&
    isNonNegativeInteger(value.reviewed_count) &&
    isNonNegativeInteger(value.total_reviewable_count) &&
    value.reviewed_count <= value.total_reviewable_count
  )
}

export function isImplementationContractJob(
  value: unknown
): value is ImplementationContractJob {
  return (
    isExactRecord(value, [
      'id',
      'document_id',
      'requested_research_map_version_id',
      'contract_version_id',
      'status',
      'stage',
      'progress',
      'error_message',
      'attempt_count',
      'created_at',
      'updated_at'
    ]) &&
    isString(value.id) &&
    isString(value.document_id) &&
    isNullableString(value.requested_research_map_version_id) &&
    isNullableString(value.contract_version_id) &&
    isOneOf(value.status, jobStatuses) &&
    isString(value.stage) &&
    isFiniteNumber(value.progress) &&
    value.progress >= 0 &&
    value.progress <= 100 &&
    isNullableString(value.error_message) &&
    isNonNegativeInteger(value.attempt_count) &&
    isIsoDate(value.created_at) &&
    isIsoDate(value.updated_at)
  )
}

export function isImplementationContract(
  value: unknown
): value is ImplementationContract {
  return (
    isExactRecord(value, [...contractBaseKeys, 'is_resolvable', 'items', 'issues']) &&
    isContractBase(value) &&
    isBoolean(value.is_resolvable) &&
    Array.isArray(value.items) &&
    value.items.every(isImplementationContractItem) &&
    Array.isArray(value.issues) &&
    value.issues.every(isContractIssue)
  )
}

export function isImplementationContractVersionArray(
  value: unknown
): value is ImplementationContractVersion[] {
  return Array.isArray(value) && value.every(isImplementationContractVersion)
}

export function isContractResolution(value: unknown): value is ContractResolution {
  if (
    !isExactRecord(value, [
      'id',
      'item_id',
      'revision_number',
      'supersedes_resolution_id',
      'status',
      'resolved_value',
      'reason',
      'based_on_contract_version_id',
      'based_on_item_signature',
      'request_id',
      'resolved_at'
    ]) ||
    !isString(value.id) ||
    !isString(value.item_id) ||
    !isPositiveInteger(value.revision_number) ||
    !isNullableString(value.supersedes_resolution_id) ||
    !isOneOf(value.status, resolutionStatuses) ||
    !(value.resolved_value === null || isContractValue(value.resolved_value)) ||
    !isNullableString(value.reason) ||
    !isString(value.based_on_contract_version_id) ||
    !isHexHash(value.based_on_item_signature) ||
    !isString(value.request_id) ||
    !isIsoDate(value.resolved_at)
  ) {
    return false
  }
  const hasReason = value.reason !== null && value.reason.trim().length > 0
  if (value.status === 'corrected' || value.status === 'decided') {
    return value.resolved_value !== null && hasReason
  }
  if (value.status === 'not_applicable') {
    return value.resolved_value === null && hasReason
  }
  return value.resolved_value === null
}

export function isImplementationContractDiff(
  value: unknown
): value is ImplementationContractDiff {
  return (
    isExactRecord(value, ['version_id', 'against_version_id', 'items']) &&
    isString(value.version_id) &&
    isString(value.against_version_id) &&
    Array.isArray(value.items) &&
    value.items.every(
      (item) =>
        isExactRecord(item, [
          'item_key',
          'classification',
          'version_item_id',
          'against_item_id'
        ]) &&
        isString(item.item_key) &&
        isOneOf(item.classification, diffClassifications) &&
        isNullableString(item.version_item_id) &&
        isNullableString(item.against_item_id)
    )
  )
}

const contractBaseKeys = [
  'id',
  'document_id',
  'research_map_version_id',
  'previous_version_id',
  'source_content_hash',
  'research_map_signature',
  'schema_version',
  'provider',
  'model_name',
  'status',
  'readiness',
  'is_active',
  'is_current',
  'is_stale',
  'created_at',
  'completed_at'
] as const

function isImplementationContractVersion(
  value: unknown
): value is ImplementationContractVersion {
  return isExactRecord(value, contractBaseKeys) && isContractBase(value)
}

function isContractBase(value: Record<string, unknown>): boolean {
  return (
    isString(value.id) &&
    isString(value.document_id) &&
    isString(value.research_map_version_id) &&
    isNullableString(value.previous_version_id) &&
    isHexHash(value.source_content_hash) &&
    isHexHash(value.research_map_signature) &&
    isString(value.schema_version) &&
    isString(value.provider) &&
    isNullableString(value.model_name) &&
    isOneOf(value.status, generationStatuses) &&
    isOneOf(value.readiness, readinessStates) &&
    isBoolean(value.is_active) &&
    isBoolean(value.is_current) &&
    isBoolean(value.is_stale) &&
    isIsoDate(value.created_at) &&
    (value.completed_at === null || isIsoDate(value.completed_at))
  )
}

function isImplementationContractItem(value: unknown): boolean {
  return (
    isExactRecord(value, [
      'id',
      'item_key',
      'section',
      'item_type',
      'draft_value',
      'effective_value',
      'origin',
      'effective_origin',
      'rationale',
      'is_blocking',
      'is_optional',
      'display_order',
      'item_signature',
      'evidence',
      'issues',
      'resolution',
      'resolution_history'
    ]) &&
    isString(value.id) &&
    isString(value.item_key) &&
    isOneOf(value.section, contractSections) &&
    isOneOf(value.item_type, contractItemTypes) &&
    (value.draft_value === null || isContractValue(value.draft_value)) &&
    (value.effective_value === null || isContractValue(value.effective_value)) &&
    isOneOf(value.origin, contractOrigins) &&
    isOneOf(value.effective_origin, contractOrigins) &&
    isNullableString(value.rationale) &&
    isBoolean(value.is_blocking) &&
    isBoolean(value.is_optional) &&
    isNonNegativeInteger(value.display_order) &&
    isHexHash(value.item_signature) &&
    Array.isArray(value.evidence) &&
    value.evidence.every(isContractEvidence) &&
    Array.isArray(value.issues) &&
    value.issues.every(isContractIssue) &&
    (value.resolution === null || isContractResolution(value.resolution)) &&
    Array.isArray(value.resolution_history) &&
    value.resolution_history.every(isContractResolution)
  )
}

function isContractEvidence(value: unknown): boolean {
  return (
    isExactRecord(value, [
      'id',
      'block_id',
      'research_node_id',
      'locator_type',
      'quote_text',
      'quote_start',
      'quote_end',
      'source_quote_hash',
      'relation',
      'source_label',
      'page_number',
      'block_type',
      'translated_text'
    ]) &&
    isString(value.id) &&
    isString(value.block_id) &&
    isNullableString(value.research_node_id) &&
    isOneOf(value.locator_type, locatorTypes) &&
    isString(value.quote_text) &&
    value.quote_text.length > 0 &&
    isNonNegativeInteger(value.quote_start) &&
    isPositiveInteger(value.quote_end) &&
    value.quote_end > value.quote_start &&
    isHexHash(value.source_quote_hash) &&
    isOneOf(value.relation, evidenceRelations) &&
    isNullableString(value.source_label) &&
    isPositiveInteger(value.page_number) &&
    isString(value.block_type) &&
    isString(value.translated_text)
  )
}

function isContractIssue(value: unknown): boolean {
  return (
    isExactRecord(value, ['id', 'item_id', 'code', 'severity', 'message']) &&
    isString(value.id) &&
    isNullableString(value.item_id) &&
    isString(value.code) &&
    isOneOf(value.severity, ['info', 'warning', 'error']) &&
    isString(value.message)
  )
}

function isContractValue(value: unknown): value is ContractValue {
  if (!isRecord(value) || !isString(value.kind)) return false
  switch (value.kind) {
    case 'scalar':
      return (
        isExactRecord(value, ['kind', 'value'], ['unit']) &&
        (isString(value.value) ||
          isBoolean(value.value) ||
          isFiniteNumber(value.value)) &&
        (!('unit' in value) || isNullableString(value.unit))
      )
    case 'formula':
      return (
        isExactRecord(value, ['kind', 'expression', 'variables']) &&
        isString(value.expression) &&
        Array.isArray(value.variables) &&
        value.variables.every(isString)
      )
    case 'rule':
      return (
        isExactRecord(value, ['kind', 'operator', 'field', 'value']) &&
        isOneOf(value.operator, ruleOperators) &&
        isString(value.field) &&
        isScalarValue(value.value)
      )
    case 'list':
      return (
        isExactRecord(value, ['kind', 'values']) &&
        Array.isArray(value.values) &&
        value.values.every(isScalarValue)
      )
    case 'range':
      return (
        isExactRecord(value, [
          'kind',
          'minimum',
          'maximum',
          'include_minimum',
          'include_maximum'
        ]) &&
        isScalarValue(value.minimum) &&
        isScalarValue(value.maximum) &&
        isBoolean(value.include_minimum) &&
        isBoolean(value.include_maximum)
      )
    case 'period':
      return (
        isExactRecord(value, ['kind', 'amount', 'unit'], ['anchor']) &&
        isPositiveInteger(value.amount) &&
        isOneOf(value.unit, periodUnits) &&
        (!('anchor' in value) || isNullableString(value.anchor))
      )
    default:
      return false
  }
}

function isScalarValue(value: unknown): boolean {
  return isContractValue(value) && value.kind === 'scalar'
}

function isExactRecord(
  value: unknown,
  requiredKeys: readonly string[],
  optionalKeys: readonly string[] = []
): value is Record<string, unknown> {
  if (!isRecord(value)) return false
  const allowed = new Set([...requiredKeys, ...optionalKeys])
  return (
    requiredKeys.every((key) => key in value) &&
    Object.keys(value).every((key) => allowed.has(key))
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOneOf<T extends string>(value: unknown, allowed: readonly T[]): value is T {
  return typeof value === 'string' && allowed.some((item) => item === value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value)
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isPositiveInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value) && value > 0
}

function isNonNegativeInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value) && value >= 0
}

function isHexHash(value: unknown): value is string {
  return isString(value) && /^[0-9a-f]{64}$/.test(value)
}

function isIsoDate(value: unknown): value is string {
  return (
    isString(value) &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value
    ) &&
    !Number.isNaN(Date.parse(value))
  )
}
