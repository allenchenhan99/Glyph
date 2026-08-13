import type {
  ContractOrigin,
  ContractReadiness,
  ContractSection,
  ContractValue,
  ImplementationContractItem
} from './types'

export const contractSectionDefinitions: ReadonlyArray<{
  key: ContractSection
  label: string
}> = [
  { key: 'thesis', label: '研究論點' },
  { key: 'data_requirements', label: '資料需求' },
  { key: 'universe_and_sample', label: '投資範圍與樣本' },
  { key: 'signal_and_timing', label: '訊號與時點' },
  { key: 'portfolio_construction', label: '投資組合建構' },
  { key: 'evaluation', label: '評估' },
  { key: 'frictions_and_risks', label: '交易摩擦與風險' },
  { key: 'open_decisions', label: '待決事項' }
]

export function contractItemTypeLabel(
  value: ImplementationContractItem['item_type']
): string {
  const label = value.replaceAll('_', ' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export function contractOriginLabel(value: ContractOrigin): string {
  const labels: Record<ContractOrigin, string> = {
    author_explicit: '作者明示',
    derived: '推導',
    human_decision: '人為決策',
    missing: '缺失'
  }
  return labels[value]
}

export function contractReadinessLabel(value: ContractReadiness): string {
  const labels: Record<ContractReadiness, string> = {
    blocked: '尚未可實作',
    review_needed: '需要人工審查',
    implementation_ready: '可進入實作'
  }
  return labels[value]
}

export function contractValueLabel(value: ContractValue | null): string {
  if (value === null) return '未提供'
  switch (value.kind) {
    case 'scalar':
      return `${String(value.value)}${value.unit ? ` ${value.unit}` : ''}`
    case 'formula':
      return value.expression
    case 'rule':
      return `${value.operator} ${value.field}: ${contractValueLabel(value.value)}`
    case 'list':
      return value.values.map(contractValueLabel).join(', ')
    case 'range':
      return `${value.include_minimum ? '[' : '('}${contractValueLabel(value.minimum)}, ${contractValueLabel(value.maximum)}${value.include_maximum ? ']' : ')'}`
    case 'period':
      return `${value.amount} ${value.unit}${value.anchor ? ` from ${value.anchor}` : ''}`
  }
}
