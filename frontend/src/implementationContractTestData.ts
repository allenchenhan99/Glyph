import type {
  ContractEvidence,
  ContractResolution,
  ImplementationContract,
  ImplementationContractDiff,
  ImplementationContractJob,
  ImplementationContractSummary,
  ImplementationContractVersion
} from './types'

const hash = (character: string) => character.repeat(64)

const evidence = (
  id: string,
  blockId: string,
  quote: string
): ContractEvidence => ({
  id,
  block_id: blockId,
  research_node_id: 'node-1',
  locator_type: 'text_span',
  quote_text: quote,
  quote_start: 0,
  quote_end: quote.length,
  source_quote_hash: hash('a'),
  relation: 'supports',
  source_label: 'Source evidence',
  page_number: 1,
  block_type: 'paragraph',
  translated_text: `繁中：${quote}`
})

const directEvidence = evidence(
  'contract-evidence-1',
  'block-1',
  'The signal uses lagged book-to-market.'
)
const secondEvidence = evidence(
  'contract-evidence-2',
  'block-2',
  'Accounting data become available after six months.'
)

const baseItem = {
  rationale: null,
  is_blocking: true,
  is_optional: false,
  item_signature: hash('b'),
  evidence: [directEvidence],
  issues: [],
  resolution: null,
  resolution_history: []
}

export const contractResolution = {
  id: 'resolution-1',
  item_id: 'item-portfolio',
  revision_number: 1,
  supersedes_resolution_id: null,
  status: 'decided',
  resolved_value: { kind: 'scalar', value: 'value_weight' },
  reason: 'Use the paper’s reported value-weighted construction.',
  based_on_contract_version_id: 'contract-1',
  based_on_item_signature: hash('c'),
  request_id: 'decision-1',
  resolved_at: '2026-08-12T12:05:00Z'
} satisfies ContractResolution

export const implementationContract = {
  id: 'contract-1',
  document_id: 'doc-1',
  research_map_version_id: 'map-1',
  previous_version_id: null,
  source_content_hash: hash('d'),
  research_map_signature: hash('e'),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  readiness: 'blocked',
  is_active: true,
  is_resolvable: true,
  is_current: true,
  is_stale: false,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:01:00Z',
  items: [
    {
      ...baseItem,
      id: 'item-thesis',
      item_key: 'signal_direction.1',
      section: 'thesis',
      item_type: 'signal_direction',
      draft_value: { kind: 'scalar', value: 'high_minus_low' },
      effective_value: { kind: 'scalar', value: 'high_minus_low' },
      origin: 'author_explicit',
      effective_origin: 'author_explicit',
      display_order: 0
    },
    {
      ...baseItem,
      id: 'item-data',
      item_key: 'required_dataset.1',
      section: 'data_requirements',
      item_type: 'required_dataset',
      draft_value: {
        kind: 'list',
        values: [
          { kind: 'scalar', value: 'Compustat' },
          { kind: 'scalar', value: 'CRSP' }
        ]
      },
      effective_value: {
        kind: 'list',
        values: [
          { kind: 'scalar', value: 'Compustat' },
          { kind: 'scalar', value: 'CRSP' }
        ]
      },
      origin: 'derived',
      effective_origin: 'derived',
      rationale: 'Two source anchors jointly identify the required datasets.',
      evidence: [directEvidence, secondEvidence],
      display_order: 0
    },
    {
      ...baseItem,
      id: 'item-universe',
      item_key: 'universe_filter.1',
      section: 'universe_and_sample',
      item_type: 'universe_filter',
      draft_value: null,
      effective_value: null,
      origin: 'missing',
      effective_origin: 'missing',
      evidence: [],
      display_order: 0,
      issues: [
        {
          id: 'issue-universe',
          item_id: 'item-universe',
          code: 'missing_blocker',
          severity: 'error',
          message: 'A blocking implementation value remains missing.'
        }
      ]
    },
    {
      ...baseItem,
      id: 'item-signal',
      item_key: 'signal_formula.1',
      section: 'signal_and_timing',
      item_type: 'signal_formula',
      draft_value: {
        kind: 'formula',
        expression: 'book_equity / market_equity',
        variables: ['book_equity', 'market_equity']
      },
      effective_value: {
        kind: 'formula',
        expression: 'book_equity / market_equity',
        variables: ['book_equity', 'market_equity']
      },
      origin: 'author_explicit',
      effective_origin: 'author_explicit',
      display_order: 0
    },
    {
      ...baseItem,
      id: 'item-portfolio',
      item_key: 'weighting_rule.1',
      section: 'portfolio_construction',
      item_type: 'weighting_rule',
      draft_value: null,
      effective_value: { kind: 'scalar', value: 'value_weight' },
      origin: 'missing',
      effective_origin: 'human_decision',
      item_signature: hash('c'),
      evidence: [],
      display_order: 0,
      resolution: contractResolution,
      resolution_history: [contractResolution]
    },
    {
      ...baseItem,
      id: 'item-evaluation',
      item_key: 'evaluation_metric.1',
      section: 'evaluation',
      item_type: 'evaluation_metric',
      draft_value: { kind: 'scalar', value: 'factor_alpha' },
      effective_value: { kind: 'scalar', value: 'factor_alpha' },
      origin: 'author_explicit',
      effective_origin: 'author_explicit',
      display_order: 0
    },
    {
      ...baseItem,
      id: 'item-friction',
      item_key: 'transaction_cost.1',
      section: 'frictions_and_risks',
      item_type: 'transaction_cost',
      draft_value: null,
      effective_value: null,
      origin: 'missing',
      effective_origin: 'missing',
      evidence: [],
      display_order: 0,
      issues: [
        {
          id: 'issue-friction',
          item_id: 'item-friction',
          code: 'missing_blocker',
          severity: 'error',
          message: 'Transaction costs require a human decision.'
        }
      ]
    },
    {
      ...baseItem,
      id: 'item-open',
      item_key: 'sample_filter.1',
      section: 'open_decisions',
      item_type: 'sample_filter',
      draft_value: null,
      effective_value: null,
      origin: 'missing',
      effective_origin: 'missing',
      is_blocking: false,
      is_optional: true,
      evidence: [],
      display_order: 0
    }
  ],
  issues: [
    {
      id: 'issue-universe',
      item_id: 'item-universe',
      code: 'missing_blocker',
      severity: 'error',
      message: 'A blocking implementation value remains missing.'
    },
    {
      id: 'issue-friction',
      item_id: 'item-friction',
      code: 'missing_blocker',
      severity: 'error',
      message: 'Transaction costs require a human decision.'
    }
  ]
} satisfies ImplementationContract

export const implementationContractVersion = {
  id: implementationContract.id,
  document_id: implementationContract.document_id,
  research_map_version_id: implementationContract.research_map_version_id,
  previous_version_id: implementationContract.previous_version_id,
  source_content_hash: implementationContract.source_content_hash,
  research_map_signature: implementationContract.research_map_signature,
  schema_version: implementationContract.schema_version,
  provider: implementationContract.provider,
  model_name: implementationContract.model_name,
  status: implementationContract.status,
  readiness: implementationContract.readiness,
  is_active: implementationContract.is_active,
  is_current: implementationContract.is_current,
  is_stale: implementationContract.is_stale,
  created_at: implementationContract.created_at,
  completed_at: implementationContract.completed_at
} satisfies ImplementationContractVersion

export const implementationContractJob = {
  id: 'contract-job-1',
  document_id: 'doc-1',
  requested_research_map_version_id: 'map-1',
  contract_version_id: null,
  status: 'queued',
  stage: 'queued',
  progress: 0,
  error_message: null,
  attempt_count: 0,
  created_at: '2026-08-12T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z'
} satisfies ImplementationContractJob

export const implementationContractDiff = {
  version_id: 'contract-1',
  against_version_id: 'contract-0',
  items: [
    {
      item_key: 'signal_formula.1',
      classification: 'value_changed',
      version_item_id: 'item-signal',
      against_item_id: 'item-signal-old'
    }
  ]
} satisfies ImplementationContractDiff

export const implementationContractSummary = {
  version_id: 'contract-1',
  generation_status: 'partial',
  readiness: 'blocked',
  is_current: true,
  is_stale: false,
  blocker_count: 2,
  reviewed_count: 1,
  total_reviewable_count: 8
} satisfies ImplementationContractSummary
