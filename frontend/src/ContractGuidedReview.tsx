import { ArrowLeft, ArrowRight, LocateFixed } from 'lucide-react'

import {
  contractItemTypeLabel,
  contractOriginLabel,
  contractSectionDefinitions,
  contractValueLabel
} from './contractPresentation'
import type {
  ContractSection,
  ImplementationContract,
  ImplementationContractItem
} from './types'

type ContractGuidedReviewProps = {
  contract: ImplementationContract
  step: number
  onPrevious: () => void
  onNext: () => void
  onInspectItem: (itemId: string) => void
}

type ReviewStage = {
  title: string
  description: string
  sections: readonly ContractSection[]
  includeAllBlockers?: boolean
}

const reviewStages: readonly ReviewStage[] = [
  {
    title: '資料可得性',
    description: '確認資料來源、欄位、頻率與可得性落後是否足以重建研究。',
    sections: ['data_requirements']
  },
  {
    title: '樣本與投資範圍',
    description: '確認樣本期間、投資範圍與篩選規則是否明確。',
    sections: ['universe_and_sample']
  },
  {
    title: '訊號與時間規則',
    description: '核對訊號公式、方向、形成日與所有時間視窗。',
    sections: ['thesis', 'signal_and_timing']
  },
  {
    title: '投資組合建構',
    description: '確認排序、權重、再平衡與持有規則能直接交付工程。',
    sections: ['portfolio_construction']
  },
  {
    title: '評估與交易摩擦',
    description: '檢查評估模型、統計檢定、成本與實務風險。',
    sections: ['evaluation', 'frictions_and_risks']
  },
  {
    title: '解決阻擋項目並匯出',
    description: '逐一處理仍會阻擋實作的條款，再產出可稽核交接文件。',
    sections: ['open_decisions'],
    includeAllBlockers: true
  }
]

export function ContractGuidedReview({
  contract,
  step,
  onPrevious,
  onNext,
  onInspectItem
}: ContractGuidedReviewProps) {
  const safeStep = Math.max(0, Math.min(reviewStages.length - 1, step))
  const stage = reviewStages[safeStep]
  const items = stageItems(contract.items, stage)
  const strongestBlocker = items
    .flatMap((item) => item.issues)
    .find((issue) => issue.severity === 'error')

  return (
    <section className="contract-guided-review" aria-labelledby="contract-guided-title">
      <header className="contract-guided-header">
        <p className="step-count">步驟 {safeStep + 1} / {reviewStages.length}</p>
        <h2 id="contract-guided-title">{stage.title}</h2>
        <p>{stage.description}</p>
        <ol className="contract-stepper" aria-label="Implementation review progress">
          {reviewStages.map((item, index) => (
            <li aria-current={index === safeStep ? 'step' : undefined} key={item.title}>
              <span>{index + 1}</span>
              <small>{item.title}</small>
            </li>
          ))}
        </ol>
      </header>

      {strongestBlocker ? (
        <div className="contract-blocker-callout" role="alert">
          <strong>Strongest blocker</strong>
          <span>{strongestBlocker.message}</span>
        </div>
      ) : null}

      <div className="contract-stage-items">
        {items.length ? (
          items.map((item) => (
            <GuidedContractItem item={item} key={item.id} onInspect={onInspectItem} />
          ))
        ) : (
          <p className="contract-stage-empty">這個步驟目前沒有條款。</p>
        )}
      </div>

      <footer className="guided-controls">
        <button
          type="button"
          className="text-button"
          disabled={safeStep === 0}
          onClick={onPrevious}
          aria-label="Previous contract review step"
        >
          <ArrowLeft aria-hidden="true" size={16} /> 上一步
        </button>
        <span>{items.length} item{items.length === 1 ? '' : 's'} in this step</span>
        <button
          type="button"
          className="text-button"
          disabled={safeStep === reviewStages.length - 1}
          onClick={onNext}
          aria-label="Next contract review step"
        >
          下一步 <ArrowRight aria-hidden="true" size={16} />
        </button>
      </footer>
    </section>
  )
}

function GuidedContractItem({
  item,
  onInspect
}: {
  item: ImplementationContractItem
  onInspect: (itemId: string) => void
}) {
  const section = contractSectionDefinitions.find((value) => value.key === item.section)
  return (
    <article className="contract-stage-item">
      <div>
        <p className="field-label">{section?.label}</p>
        <h3>{contractItemTypeLabel(item.item_type)}</h3>
        <p className="contract-stage-value">{contractValueLabel(item.effective_value)}</p>
        <span className={`contract-origin origin-${item.effective_origin}`}>
          {contractOriginLabel(item.effective_origin)}
        </span>
      </div>
      {item.evidence.map((evidence) => (
        <blockquote key={evidence.id}>{evidence.quote_text}</blockquote>
      ))}
      <button
        type="button"
        className="strongest-evidence"
        onClick={() => onInspect(item.id)}
        aria-label={`Inspect ${contractItemTypeLabel(item.item_type)}`}
      >
        <span className="evidence-rail-mark" aria-hidden="true">
          <LocateFixed size={16} />
        </span>
        <span>Inspect evidence and decision</span>
      </button>
    </article>
  )
}

function stageItems(
  items: ImplementationContractItem[],
  stage: ReviewStage
): ImplementationContractItem[] {
  const selected = items.filter((item) => stage.sections.includes(item.section))
  if (!stage.includeAllBlockers) return selected
  const blockers = items.filter(
    (item) => item.is_blocking && item.effective_value === null
  )
  return [...new Map([...blockers, ...selected].map((item) => [item.id, item])).values()]
}
