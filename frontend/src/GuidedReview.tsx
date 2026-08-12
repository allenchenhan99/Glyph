import { ArrowLeft, ArrowRight, LocateFixed } from 'lucide-react'

import type { ResearchMap, ResearchMapIssue, ResearchNode, ResearchNodeType } from './types'

type GuidedReviewProps = {
  map: ResearchMap
  step: number
  onPrevious: () => void
  onNext: () => void
  onInspectEvidence: (nodeId: string) => void
}

type GuidedStage = {
  title: string
  description: string
  types: readonly ResearchNodeType[]
  issueCategory: string
}

const guidedStages: readonly GuidedStage[] = [
  {
    title: 'Research question',
    description: 'What does the paper claim it is trying to explain or test?',
    types: ['research_question', 'author_claim', 'hypothesis', 'economic_mechanism'],
    issueCategory: 'question'
  },
  {
    title: 'Data and sample',
    description: 'Which observations, sources, dates, and filters define the evidence?',
    types: ['data_and_sample', 'data_source', 'sample_filter'],
    issueCategory: 'data'
  },
  {
    title: 'Signal and portfolio construction',
    description: 'How is the signal defined and turned into an investable test?',
    types: ['signal_definition', 'variable_definition', 'portfolio_construction', 'rebalancing_rule'],
    issueCategory: 'signal'
  },
  {
    title: 'Method and main result',
    description: 'What is the main empirical result and how was it estimated?',
    types: [
      'primary_result',
      'statistical_evidence',
      'economic_magnitude',
      'empirical_method',
      'benchmark_model',
      'identification_strategy'
    ],
    issueCategory: 'result'
  },
  {
    title: 'Limitations and implementation gaps',
    description: 'What remains uncertain, costly, unreported, or difficult to implement?',
    types: [
      'limitations',
      'implementation_constraint',
      'transaction_cost',
      'alternative_explanation',
      'unanswered_question'
    ],
    issueCategory: 'limitations'
  }
]

export function GuidedReview({
  map,
  step,
  onPrevious,
  onNext,
  onInspectEvidence
}: GuidedReviewProps) {
  const safeStep = Math.max(0, Math.min(guidedStages.length - 1, step))
  const stage = guidedStages[safeStep]
  const node = strongestNode(map.nodes, stage.types)
  const issue = node ? null : stageIssue(map.issues, stage.issueCategory)
  const strongestEvidence = node ? strongestAnchor(node) : null

  return (
    <section className="guided-review" aria-labelledby="guided-review-title">
      <header className="guided-header">
        <div>
          <p className="step-count">Step {safeStep + 1} of {guidedStages.length}</p>
          <h2 id="guided-review-title">{stage.title}</h2>
          <p>{stage.description}</p>
        </div>
        <ol className="review-stepper" aria-label="Ten-minute review progress">
          {guidedStages.map((item, index) => (
            <li aria-current={index === safeStep ? 'step' : undefined} key={item.title}>
              <span>{index + 1}</span>
              <small>{item.title}</small>
            </li>
          ))}
        </ol>
      </header>

      {node ? (
        <article className="guided-claim">
          <div className="claim-index" aria-hidden="true">0{safeStep + 1}</div>
          <div>
            <p className="field-label">Concise conclusion</p>
            <h3>{node.effective_claim_text}</h3>
            {node.explanation ? <p>{node.explanation}</p> : null}
            <div className="claim-tags">
              <span>{provenanceLabel(node.provenance)}</span>
              <span>{qualityLabel(node.evidence_quality)}</span>
              {node.review ? <span className="reviewed-tag">Human {node.review.status}</span> : null}
            </div>
          </div>
        </article>
      ) : (
        <div className="guided-gap" role="alert">
          <strong>No supported conclusion for this step.</strong>
          <p>{issue?.message ?? `The Research Map has no supported ${stage.title.toLowerCase()} node.`}</p>
        </div>
      )}

      {node && strongestEvidence ? (
        <button
          type="button"
          className="strongest-evidence"
          onClick={() => onInspectEvidence(node.id)}
          aria-label={`Inspect strongest evidence for ${node.title}`}
        >
          <span className="evidence-rail-mark" aria-hidden="true"><LocateFixed size={16} /></span>
          <span>
            <span className="field-label">Strongest exact evidence</span>
            <q>{strongestEvidence.quote_text}</q>
            <small>Page {strongestEvidence.page_number} · {relationLabel(strongestEvidence.relation)}</small>
          </span>
        </button>
      ) : null}

      <footer className="guided-controls">
        <button
          type="button"
          className="text-button"
          disabled={safeStep === 0}
          onClick={onPrevious}
          aria-label="Previous review step"
        >
          <ArrowLeft aria-hidden="true" size={16} /> Previous
        </button>
        <span>{map.reviewed_core_nodes} / {map.reviewable_core_nodes} core nodes reviewed</span>
        <button
          type="button"
          className="text-button"
          disabled={safeStep === guidedStages.length - 1}
          onClick={onNext}
          aria-label="Next review step"
        >
          Next <ArrowRight aria-hidden="true" size={16} />
        </button>
      </footer>
    </section>
  )
}

function strongestNode(nodes: ResearchNode[], types: readonly ResearchNodeType[]): ResearchNode | null {
  for (const type of types) {
    const supported = nodes.find(
      (node) => node.node_type === type && node.evidence.length > 0 && node.evidence_quality !== 'conflicted'
    )
    if (supported) return supported
  }
  return nodes.find((node) => types.includes(node.node_type)) ?? null
}

function strongestAnchor(node: ResearchNode) {
  return (
    node.evidence.find((item) => item.relation === 'supports') ??
    node.evidence.find((item) => item.relation === 'qualifies') ??
    node.evidence[0] ??
    null
  )
}

function stageIssue(issues: ResearchMapIssue[], category: string): ResearchMapIssue | null {
  return (
    issues.find(
      (issue) =>
        issue.code === 'missing_core_node' && issue.message.toLowerCase().includes(category)
    ) ?? null
  )
}

export function provenanceLabel(value: ResearchNode['provenance']): string {
  if (value === 'author_explicit') return 'Author explicit'
  if (value === 'ai_synthesis') return 'AI synthesis'
  return 'Human created'
}

export function qualityLabel(value: ResearchNode['evidence_quality']): string {
  const labels: Record<ResearchNode['evidence_quality'], string> = {
    direct: 'Direct evidence',
    synthesized: 'Synthesized evidence',
    insufficient: 'Insufficient evidence',
    conflicted: 'Conflicting evidence',
    not_reported: 'Not reported'
  }
  return labels[value]
}

export function relationLabel(value: ResearchNode['evidence'][number]['relation']): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}
