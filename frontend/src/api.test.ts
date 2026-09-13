import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  getDocumentSummaries,
  generateDocumentSummaries,
  getProcessingPreflight,
  listProcessingJobs,
  cancelProcessingJob,
  getAiSettings,
  updateAiSettings,
  activateImplementationContract,
  activateResearchMap,
  enqueueImplementationContract,
  enqueueResearchMap,
  getActiveResearchMap,
  getActiveImplementationContract,
  getImplementationContractDiff,
  getImplementationContractExport,
  getImplementationContractJob,
  getImplementationContractVersion,
  getResearchMapDiff,
  getResearchMapJob,
  getResearchMapVersion,
  listDocuments,
  listImplementationContractVersions,
  listResearchMapVersions,
  processDocument,
  resolveImplementationContractItem,
  reviewResearchNode
} from './api'
import {
  contractResolution,
  implementationContract,
  implementationContractDiff,
  implementationContractJob,
  implementationContractSummary,
  implementationContractVersion
} from './implementationContractTestData'

describe('document summary contract', () => {
  it('loads state and explicitly starts generation', async () => {
    const state = { status: 'not_generated', provider: 'claude_cli', model: null, version: null, job: null }
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(state)))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getDocumentSummaries('d1')).resolves.toEqual(state)
    await expect(generateDocumentSummaries('d1')).resolves.toEqual(state)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/documents/d1/summaries', { method: 'POST' })
  })

  it('rejects claims that have no evidence', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: 'available', provider: 'mock', model: null, job: null,
      version: { id: 'v', source_content_hash: 'a'.repeat(64), reader_fingerprint: 'b'.repeat(64),
        provider: 'mock', model: null, created_at: '2026-09-13', claims: [{ id: 'c', section_path: null, text: 'Unsupported.', evidence: [] }] }
    }))))
    await expect(getDocumentSummaries('d1')).rejects.toThrow()
  })
})

const evidence = {
  id: 'evidence-1',
  block_id: 'block-1',
  locator_type: 'text_span',
  quote_text: 'The strategy earns 0.8 percent per month.',
  quote_start: 0,
  quote_end: 43,
  source_quote_hash: 'a'.repeat(64),
  relation: 'supports',
  source_label: 'Primary result',
  page_number: 7,
  block_type: 'paragraph',
  translated_text: '此策略每月報酬為 0.8%。'
}

const node = {
  id: 'node-1',
  parent_node_id: null,
  node_key: 'primary_result.1',
  node_type: 'primary_result',
  title: '主要結果',
  claim_text: 'The strategy earns 0.8 percent per month.',
  effective_claim_text: 'The strategy earns 0.8 percent per month.',
  explanation: 'Long-short return.',
  provenance: 'author_explicit',
  evidence_quality: 'direct',
  display_order: 0,
  node_signature: 'b'.repeat(64),
  evidence: [evidence],
  issues: [],
  review: null
}

const researchMap = {
  id: 'map-1',
  document_id: 'doc-1',
  previous_version_id: null,
  source_content_hash: 'c'.repeat(64),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  is_active: true,
  is_current: true,
  is_stale: false,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z',
  reviewed_core_nodes: 0,
  reviewable_core_nodes: 1,
  nodes: [node],
  issues: [
    {
      id: 'issue-1',
      node_id: 'node-1',
      code: 'not_reported',
      severity: 'warning',
      message: 'Transaction costs are not reported.'
    }
  ]
}

const job = {
  id: 'job-1',
  document_id: 'doc-1',
  map_version_id: null,
  status: 'queued',
  stage: 'queued',
  progress: 0,
  error_message: null,
  attempt_count: 0,
  created_at: '2026-08-12T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z'
}

const review = {
  id: 'review-1',
  node_id: 'node-1',
  status: 'confirmed',
  corrected_claim_text: null,
  review_note: 'Checked.',
  revision_number: 1,
  supersedes_review_id: null,
  reviewed_at: '2026-08-12T12:01:00Z',
  based_on_map_version_id: 'map-1',
  based_on_node_signature: 'b'.repeat(64)
}

const version = {
  id: 'map-1',
  document_id: 'doc-1',
  previous_version_id: null,
  source_content_hash: 'c'.repeat(64),
  schema_version: '1',
  provider: 'mock',
  model_name: null,
  status: 'partial',
  is_active: true,
  is_current: true,
  is_stale: false,
  created_at: '2026-08-12T12:00:00Z',
  completed_at: '2026-08-12T12:00:01Z'
}

const diff = {
  version_id: 'map-1',
  against_version_id: 'map-0',
  nodes: [
    {
      node_key: 'primary_result.1',
      classification: 'claim_changed',
      version_node_id: 'node-1',
      against_node_id: 'node-0'
    }
  ]
}

describe('API errors', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('preserves a safe JSON detail from the backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'This document is already being processed.' }), {
          status: 409,
          headers: { 'content-type': 'application/json' }
        })
      )
    )

    const request = processDocument('doc-1')

    await expect(request).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: 'ApiError',
        status: 409,
        message: 'This document is already being processed.'
      })
    )
  })

  it('uses a status fallback for a non-JSON error response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('upstream failed', {
          status: 502,
          headers: { 'content-type': 'text/plain' }
        })
      )
    )

    await expect(processDocument('doc-1')).rejects.toEqual(
      new ApiError(502, 'Request failed with 502')
    )
  })
})

describe('Research Map API contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('accepts the schema-v1 research_question ontology value', async () => {
    const questionMap = {
      ...researchMap,
      nodes: [{ ...node, node_key: 'research_question.1', node_type: 'research_question' }]
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(questionMap), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )

    await expect(getActiveResearchMap('doc-1')).resolves.toEqual(questionMap)
  })

  it('validates every typed response and sends review preconditions', async () => {
    const responses = [job, job, researchMap, researchMap, [version], review, researchMap, diff]
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(responses.shift()), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(enqueueResearchMap('doc-1')).resolves.toEqual(job)
    await expect(getResearchMapJob('job-1')).resolves.toEqual(job)
    await expect(getActiveResearchMap('doc-1')).resolves.toEqual(researchMap)
    await expect(getResearchMapVersion('map-1')).resolves.toEqual(researchMap)
    await expect(listResearchMapVersions('doc-1')).resolves.toEqual([version])
    await expect(
      reviewResearchNode('node-1', {
        status: 'confirmed',
        based_on_node_signature: 'b'.repeat(64),
        corrected_claim_text: null,
        review_note: 'Checked.'
      })
    ).resolves.toEqual(review)
    await expect(activateResearchMap('map-1')).resolves.toEqual(researchMap)
    await expect(getResearchMapDiff('map-1', 'map-0')).resolves.toEqual(diff)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/documents/doc-1/research-map', {
      method: 'POST'
    })
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      '/api/research-nodes/node-1/review',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          status: 'confirmed',
          based_on_node_signature: 'b'.repeat(64),
          corrected_claim_text: null,
          review_note: 'Checked.'
        })
      })
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      '/api/research-maps/map-1/diff?against=map-0',
      undefined
    )
  })

  it('validates optional batched Research Map summaries in document rows', async () => {
    const document = {
      id: 'doc-1',
      title: 'sample.pdf',
      file_type: 'pdf',
      status: 'completed',
      research_map: {
        version_id: 'map-1',
        status: 'partial',
        is_current: true,
        is_stale: false,
        reviewed_core_nodes: 2,
        reviewable_core_nodes: 6,
        issue_count: 3
      }
    }
    const responses = [[document], [{ ...document, research_map: { ...document.research_map, issue_count: -1 } }]]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(responses.shift()), {
            status: 200,
            headers: { 'content-type': 'application/json' }
          })
        )
      )
    )

    await expect(listDocuments()).resolves.toEqual([document])
    await expect(listDocuments()).rejects.toThrow('Unexpected API response shape')
  })

  it.each([
    ['unknown provenance', { ...node, provenance: 'model_guess' }],
    ['unknown evidence quality', { ...node, evidence_quality: 'probably_true' }],
    ['unknown node type', { ...node, node_type: 'chat_answer' }],
    [
      'malformed evidence',
      { ...node, evidence: [{ ...evidence, quote_start: -1 }] }
    ],
    ['unknown review status', { ...node, review: { ...review, status: 'approved' } }]
  ])('rejects %s at the HTTP boundary', async (_label, invalidNode) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ ...researchMap, nodes: [invalidNode] }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      )
    )

    await expect(getActiveResearchMap('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })

  it('rejects obsolete map shapes with missing structured issues', async () => {
    const { issues: _issues, ...obsoleteMap } = researchMap
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(obsoleteMap), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )

    await expect(getActiveResearchMap('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })

  it('rejects invalid job, review, version, and diff literal values', async () => {
    const invalidPayloads = [
      { ...job, status: 'sleeping' },
      { ...review, status: 'approved' },
      [{ ...version, status: 'draft' }],
      {
        ...diff,
        nodes: [{ ...diff.nodes[0], classification: 'semantically_similar' }]
      }
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(invalidPayloads.shift()), {
            status: 200,
            headers: { 'content-type': 'application/json' }
          })
        )
      )
    )

    await expect(getResearchMapJob('job-1')).rejects.toThrow('Unexpected API response shape')
    await expect(
      reviewResearchNode('node-1', {
        status: 'confirmed',
        based_on_node_signature: 'b'.repeat(64),
        corrected_claim_text: null,
        review_note: null
      })
    ).rejects.toThrow('Unexpected API response shape')
    await expect(listResearchMapVersions('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getResearchMapDiff('map-1', 'map-0')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })
})

describe('Implementation Contract API contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('validates every typed response and sends generation and resolution preconditions', async () => {
    const responses = [
      implementationContractJob,
      implementationContractJob,
      implementationContract,
      implementationContract,
      [implementationContractVersion],
      implementationContractDiff,
      contractResolution,
      implementationContract
    ]
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(responses.shift()), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(enqueueImplementationContract('doc-1', 'map-1')).resolves.toEqual(
      implementationContractJob
    )
    await expect(getImplementationContractJob('contract-job-1')).resolves.toEqual(
      implementationContractJob
    )
    await expect(getActiveImplementationContract('doc-1')).resolves.toEqual(
      implementationContract
    )
    await expect(getImplementationContractVersion('contract-1')).resolves.toEqual(
      implementationContract
    )
    await expect(listImplementationContractVersions('doc-1')).resolves.toEqual([
      implementationContractVersion
    ])
    await expect(
      getImplementationContractDiff('contract-1', 'contract-0')
    ).resolves.toEqual(implementationContractDiff)
    await expect(
      resolveImplementationContractItem('item-portfolio', {
        request_id: 'decision-1',
        status: 'decided',
        based_on_item_signature: 'c'.repeat(64),
        resolved_value: { kind: 'scalar', value: 'value_weight' },
        reason: 'Use the paper’s reported value-weighted construction.'
      })
    ).resolves.toEqual(contractResolution)
    await expect(activateImplementationContract('contract-1')).resolves.toEqual(
      implementationContract
    )

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/documents/doc-1/implementation-contract',
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ research_map_version_id: 'map-1' })
      }
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      '/api/implementation-contracts/contract-1/diff?against=contract-0',
      undefined
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      '/api/implementation-contract-items/item-portfolio/resolution',
      expect.objectContaining({ method: 'PATCH' })
    )
  })

  it('validates optional contract summaries in document rows', async () => {
    const document = {
      id: 'doc-1',
      title: 'sample.pdf',
      file_type: 'pdf',
      status: 'completed',
      research_map: null,
      implementation_contract: implementationContractSummary
    }
    const invalid = {
      ...document,
      implementation_contract: {
        ...implementationContractSummary,
        reviewed_count: 9
      }
    }
    const responses = [[document], [invalid]]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(responses.shift()), {
            status: 200,
            headers: { 'content-type': 'application/json' }
          })
        )
      )
    )

    await expect(listDocuments()).resolves.toEqual([document])
    await expect(listDocuments()).rejects.toThrow('Unexpected API response shape')
  })

  it('accepts every versioned ContractValue discriminator', async () => {
    const values = [
      { kind: 'scalar', value: 5, unit: 'percent' },
      {
        kind: 'formula',
        expression: 'book_equity / market_equity',
        variables: ['book_equity', 'market_equity']
      },
      {
        kind: 'rule',
        operator: 'include',
        field: 'exchange_code',
        value: { kind: 'scalar', value: 'NYSE' }
      },
      {
        kind: 'list',
        values: [
          { kind: 'scalar', value: 'NYSE' },
          { kind: 'scalar', value: 'NASDAQ' }
        ]
      },
      {
        kind: 'range',
        minimum: { kind: 'scalar', value: 0 },
        maximum: { kind: 'scalar', value: 1 },
        include_minimum: true,
        include_maximum: false
      },
      { kind: 'period', amount: 6, unit: 'month', anchor: 'fiscal_period_end' }
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => {
        const value = values.shift()
        const item = {
          ...implementationContract.items[0],
          draft_value: value,
          effective_value: value
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({ ...implementationContract, items: [item] }),
            { status: 200, headers: { 'content-type': 'application/json' } }
          )
        )
      })
    )

    for (let index = 0; index < 6; index += 1) {
      await expect(getActiveImplementationContract('doc-1')).resolves.toBeDefined()
    }
  })

  it.each([
    ['unknown section', { ...implementationContract.items[0], section: 'alpha' }],
    ['unknown type', { ...implementationContract.items[0], item_type: 'magic' }],
    ['unknown origin', { ...implementationContract.items[0], origin: 'model_guess' }],
    [
      'unknown effective origin',
      { ...implementationContract.items[0], effective_origin: 'model_guess' }
    ],
    [
      'unknown typed-value key',
      {
        ...implementationContract.items[0],
        draft_value: { kind: 'scalar', value: 1, default: 0 }
      }
    ],
    [
      'malformed typed value',
      {
        ...implementationContract.items[0],
        draft_value: { kind: 'formula', expression: 'x' }
      }
    ],
    [
      'non-finite typed number',
      {
        ...implementationContract.items[0],
        draft_value: { kind: 'scalar', value: Number.POSITIVE_INFINITY }
      }
    ],
    [
      'invalid evidence hash',
      {
        ...implementationContract.items[0],
        evidence: [
          { ...implementationContract.items[0].evidence[0], source_quote_hash: 'bad' }
        ]
      }
    ],
    [
      'incomplete evidence',
      {
        ...implementationContract.items[0],
        evidence: [{ id: 'evidence-only' }]
      }
    ],
    [
      'incomplete resolution',
      {
        ...implementationContract.items[4],
        resolution: { id: 'resolution-only' }
      }
    ]
  ])('rejects %s at the HTTP boundary', async (_label, invalidItem) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ ...implementationContract, items: [invalidItem] }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      )
    )

    await expect(getActiveImplementationContract('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
  })

  it('rejects invalid contract, job, resolution, version, and diff metadata', async () => {
    const invalidPayloads = [
      { ...implementationContract, readiness: 'probably_ready' },
      { ...implementationContract, status: 'draft' },
      { ...implementationContract, created_at: 'tomorrow' },
      { ...implementationContract, internal_provider_trace: 'must not escape' },
      { ...implementationContractJob, status: 'sleeping' },
      { ...implementationContractJob, progress: Number.NaN },
      { ...contractResolution, status: 'approved' },
      [{ ...implementationContractVersion, research_map_signature: 'bad' }],
      {
        ...implementationContractDiff,
        items: [
          {
            ...implementationContractDiff.items[0],
            classification: 'semantically_similar'
          }
        ]
      }
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(invalidPayloads.shift()), {
            status: 200,
            headers: { 'content-type': 'application/json' }
          })
        )
      )
    )

    await expect(getActiveImplementationContract('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getActiveImplementationContract('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getActiveImplementationContract('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getActiveImplementationContract('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getImplementationContractJob('job-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(getImplementationContractJob('job-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(
      resolveImplementationContractItem('item-1', {
        request_id: 'decision-1',
        status: 'confirmed',
        based_on_item_signature: 'b'.repeat(64),
        resolved_value: null,
        reason: null
      })
    ).rejects.toThrow('Unexpected API response shape')
    await expect(listImplementationContractVersions('doc-1')).rejects.toThrow(
      'Unexpected API response shape'
    )
    await expect(
      getImplementationContractDiff('contract-1', 'contract-0')
    ).rejects.toThrow('Unexpected API response shape')
  })

  it('downloads only complete export metadata from strict response headers', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"readiness":"blocked"}', {
        status: 200,
        headers: {
          'content-type': 'application/json',
          'content-disposition':
            'attachment; filename="implementation-contract-contract-1.json"'
        }
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const download = await getImplementationContractExport(
      'contract-1',
      'json',
      'bilingual'
    )

    expect(download.filename).toBe('implementation-contract-contract-1.json')
    expect(download.content_type).toBe('application/json')
    expect(download.blob.size).toBe(new TextEncoder().encode('{"readiness":"blocked"}').length)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/implementation-contracts/contract-1/export?format=json&language=bilingual'
    )
  })

  it.each([
    [{ 'content-type': 'application/json' }, 'missing disposition'],
    [
      {
        'content-type': 'application/json',
        'content-disposition': 'inline; filename="contract.json"'
      },
      'wrong disposition'
    ],
    [
      {
        'content-type': 'text/plain',
        'content-disposition': 'attachment; filename="contract.json"'
      },
      'wrong content type'
    ]
  ])('rejects structurally incomplete export metadata: %s', async (headers, _label) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers }))
    )

    await expect(
      getImplementationContractExport('contract-1', 'json', 'en')
    ).rejects.toThrow('Unexpected API response shape')
  })
})


describe('translation settings', () => {
  it('validates the settings response and posts keys only in the body', async () => {
    const payload = { provider: 'orcarouter', model: 'test/model', has_api_key: true, ocr_mode: 'mock' }
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(payload)))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getAiSettings()).resolves.toEqual(payload)
    await expect(updateAiSettings({ provider: 'orcarouter', model: 'test/model', api_key: 'test-key' })).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/settings/ai', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'orcarouter', model: 'test/model', api_key: 'test-key' })
    })
  })

  it('rejects an unknown provider instead of displaying an unusable form', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      provider: 'unknown', model: '', has_api_key: false, ocr_mode: 'mock'
    }))))
    await expect(getAiSettings()).rejects.toThrow('Unexpected API response shape')
  })
})


describe('document processing endpoints', () => {
  it('accepts preflight and persistent job states', async () => {
    const preflight = { ready: false, source_type: 'image', provider: 'mock', page_count: 1,
      issues: [{ code: 'ocr_required', severity: 'error', message: 'Configure OCR.' }] }
    const job = { id: 'job-1', document_id: 'doc-1', status: 'running', stage: 'translation',
      progress: 42, completed_blocks: 4, total_blocks: 10, cancel_requested: false,
      error_message: null }
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(preflight)))
      .mockResolvedValueOnce(new Response(JSON.stringify([job])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...job, cancel_requested: true })))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getProcessingPreflight('doc-1')).resolves.toEqual(preflight)
    await expect(listProcessingJobs()).resolves.toEqual([job])
    await expect(cancelProcessingJob('job-1')).resolves.toMatchObject({ cancel_requested: true })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/jobs/job-1/cancel', { method: 'POST' })
  })

  it('rejects invalid progress and malformed preflight issues', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify([
      { id: 'job-1', document_id: 'doc-1', status: 'running', stage: 'translation', progress: 200,
        error_message: null }
    ]))).mockResolvedValueOnce(new Response(JSON.stringify({ ready: true, source_type: 'image',
      provider: 'mock', page_count: null, issues: [{ severity: 'success' }] }))))
    await expect(listProcessingJobs()).rejects.toThrow('Unexpected API response shape')
    await expect(getProcessingPreflight('doc-1')).rejects.toThrow('Unexpected API response shape')
  })
})
