import { AlertTriangle, CircleCheck, FlaskConical, LocateFixed, ShieldAlert } from 'lucide-react'

import { EvidenceInspector } from './EvidenceInspector'
import { GuidedReview, provenanceLabel, qualityLabel } from './GuidedReview'
import type { ResearchMapNotice } from './researchMapState'
import type {
  ResearchMap as ResearchMapData,
  ResearchMapJob,
  ResearchNodeType,
  ReviewStatus
} from './types'

type ResearchMapProps = {
  map: ResearchMapData | null
  selectedNodeId: string | null
  guidedStep: number
  inspectorOpen: boolean
  notice: ResearchMapNotice
  job?: ResearchMapJob | null
  reviewPending?: boolean
  onSelectNode: (nodeId: string) => void
  onOpenInspector: () => void
  onCloseInspector: () => void
  onGuidedNext: () => void
  onGuidedPrevious: () => void
  onOpenReader: (blockId: string) => void
  onReview: (
    status: ReviewStatus,
    correctedClaimText: string | null,
    reviewNote: string | null
  ) => void
  onGenerate: () => void
  onBuildContract: (researchMapVersionId: string) => void
}

type OutlineCategory = {
  title: string
  types: readonly ResearchNodeType[]
}

const categories: readonly OutlineCategory[] = [
  {
    title: 'Research question',
    types: ['research_question', 'author_claim', 'hypothesis', 'economic_mechanism']
  },
  { title: 'Data and sample', types: ['data_and_sample', 'data_source', 'sample_filter'] },
  {
    title: 'Signal definition',
    types: ['signal_definition', 'variable_definition', 'portfolio_construction', 'rebalancing_rule']
  },
  {
    title: 'Empirical method',
    types: ['empirical_method', 'benchmark_model', 'identification_strategy']
  },
  {
    title: 'Primary result',
    types: ['primary_result', 'statistical_evidence', 'economic_magnitude', 'subsample_result']
  },
  {
    title: 'Limitations',
    types: [
      'limitations',
      'implementation_constraint',
      'transaction_cost',
      'turnover',
      'alternative_explanation',
      'unanswered_question',
      'robustness_test'
    ]
  }
]

export function ResearchMap({
  map,
  selectedNodeId,
  guidedStep,
  inspectorOpen,
  notice,
  job = null,
  reviewPending = false,
  onSelectNode,
  onOpenInspector,
  onCloseInspector,
  onGuidedNext,
  onGuidedPrevious,
  onOpenReader,
  onReview,
  onGenerate,
  onBuildContract
}: ResearchMapProps) {
  if (!map) {
    return (
      <section className="research-map-empty" aria-label="Research Map workspace">
        <FlaskConical aria-hidden="true" size={28} />
        <p className="kicker">Evidence-first analysis</p>
        <h2>No Research Map yet</h2>
        <p>
          Generate a structured map of the paper's question, data, signal, method, result, and
          limitations. Every supported conclusion links to an exact Reader block.
        </p>
        {job && (job.status === 'queued' || job.status === 'running') ? (
          <div className="map-job-progress" role="status">
            <div><span>{job.stage}</span><strong>{Math.round(job.progress)}%</strong></div>
            <progress value={job.progress} max="100">{job.progress}%</progress>
          </div>
        ) : (
          <button type="button" className="primary-action" onClick={onGenerate}>
            Generate Research Map
          </button>
        )}
        <p className="privacy-note">
          Paper text is processed by your configured local provider. Glyph does not upload it to a
          Glyph account or enable telemetry by default.
        </p>
      </section>
    )
  }

  const selectedNode = map.nodes.find((node) => node.id === selectedNodeId) ?? map.nodes[0] ?? null
  const generationActive = job && (job.status === 'queued' || job.status === 'running')
  const contractStatusEligible = map.status === 'complete' || map.status === 'partial'
  const contractSourceEligible = map.is_current && !map.is_stale

  return (
    <section className="research-map-shell" aria-label="Research Map workspace">
      <header className="map-statusbar">
        <div>
          <p className="kicker">Research Map · schema {map.schema_version}</p>
          <h2>Evidence-led paper review</h2>
        </div>
        <div className="trust-badges" aria-label="Map trust state">
          {map.status === 'partial' ? (
            <span className="warning-badge"><AlertTriangle aria-hidden="true" size={14} /> Partial map</span>
          ) : (
            <span className="review-badge"><CircleCheck aria-hidden="true" size={14} /> Complete map</span>
          )}
          {map.is_stale ? (
            <>
              <span className="conflict-badge"><ShieldAlert aria-hidden="true" size={14} /> Source changed</span>
              {generationActive ? (
                <div className="map-job-progress compact" role="status">
                  <div><span>{job.stage}</span><strong>{Math.round(job.progress)}%</strong></div>
                  <progress value={job.progress} max="100">{job.progress}%</progress>
                </div>
              ) : (
                <button type="button" className="primary-action" onClick={onGenerate}>
                  Generate new version
                </button>
              )}
            </>
          ) : null}
        </div>
      </header>

      {contractStatusEligible ? (
        <div className="map-contract-action">
          <button
            type="button"
            className="primary-action"
            disabled={!contractSourceEligible}
            onClick={() => onBuildContract(map.id)}
          >
            Build Implementation Contract
          </button>
          {map.is_stale ? (
            <p className="status-line">
              Refresh the source and Research Map before building a contract.
            </p>
          ) : !map.is_current ? (
            <p className="status-line">
              Activate the current Research Map version before building a contract.
            </p>
          ) : null}
        </div>
      ) : null}

      {notice ? (
        <p className={notice.kind === 'error' ? 'map-alert' : 'map-status'} role={notice.kind === 'error' ? 'alert' : 'status'}>
          {notice.message}
        </p>
      ) : null}
      {map.issues.length ? (
        <div className="map-issues" role={notice?.kind === 'error' ? 'note' : 'alert'}>
          <strong>{map.issues.length} evidence gap{map.issues.length === 1 ? '' : 's'}</strong>
          <span>{map.issues.map((issue) => issue.message).join(' ')}</span>
        </div>
      ) : null}

      <div className={inspectorOpen ? 'map-workbench' : 'map-workbench inspector-collapsed'}>
        <nav className="ontology-outline" aria-label="Research Map outline">
          <div className="outline-progress">
            <span>{map.reviewed_core_nodes} / {map.reviewable_core_nodes}</span>
            <small>human-reviewed core nodes</small>
          </div>
          {categories.map((category) => {
            const nodes = map.nodes.filter((node) => category.types.includes(node.node_type))
            return (
              <section className="outline-category" key={category.title}>
                <h3>{category.title}</h3>
                {nodes.length ? (
                  nodes.map((node) => (
                    <button
                      type="button"
                      className={node.id === selectedNode?.id ? 'outline-node selected' : 'outline-node'}
                      aria-label={node.title}
                      aria-current={node.id === selectedNode?.id ? 'true' : undefined}
                      onClick={() => onSelectNode(node.id)}
                      key={node.id}
                    >
                      <span>{node.title}</span>
                      <small>{node.review ? node.review.status : qualityLabel(node.evidence_quality)}</small>
                    </button>
                  ))
                ) : (
                  <p className="outline-gap">No supported node</p>
                )}
              </section>
            )
          })}
        </nav>

        <section className="map-review-main" aria-label="Guided Research Map review">
          <GuidedReview
            map={map}
            step={guidedStep}
            onPrevious={onGuidedPrevious}
            onNext={onGuidedNext}
            onInspectEvidence={(nodeId) => {
              onSelectNode(nodeId)
              onOpenInspector()
            }}
          />

          {selectedNode ? (
            <section className="selected-node-summary" aria-labelledby="selected-node-title">
              <div>
                <p className="field-label">Selected map node</p>
                <h2 id="selected-node-title">{selectedNode.title}</h2>
                <p>{selectedNode.effective_claim_text}</p>
                <div className="claim-tags">
                  <span>{provenanceLabel(selectedNode.provenance)}</span>
                  <span>{qualityLabel(selectedNode.evidence_quality)}</span>
                </div>
              </div>
              {!inspectorOpen ? (
                <button type="button" className="reader-link" onClick={onOpenInspector}>
                  <LocateFixed aria-hidden="true" size={16} /> Inspect evidence
                </button>
              ) : null}
            </section>
          ) : null}
        </section>

        {inspectorOpen && selectedNode ? (
          <EvidenceInspector
            node={selectedNode}
            reviewPending={reviewPending}
            onClose={onCloseInspector}
            onOpenReader={onOpenReader}
            onReview={onReview}
          />
        ) : null}
      </div>
    </section>
  )
}
