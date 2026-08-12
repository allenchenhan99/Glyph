import { AlertTriangle, CircleCheck, LocateFixed, ShieldAlert } from 'lucide-react'
import { useState } from 'react'

import { ContractExport } from './ContractExport'
import { ContractGuidedReview } from './ContractGuidedReview'
import { ContractInspector } from './ContractInspector'
import { ContractVersions } from './ContractVersions'
import {
  contractItemTypeLabel,
  contractOriginLabel,
  contractReadinessLabel,
  contractSectionDefinitions,
  contractValueLabel
} from './contractPresentation'
import type { ContractNotice } from './implementationContractState'
import type {
  ContractResolutionStatus,
  ContractExportFormat,
  ContractExportLanguage,
  ContractValue,
  ImplementationContract as ImplementationContractData,
  ImplementationContractDiff,
  ImplementationContractExport,
  ImplementationContractVersion
} from './types'

type ImplementationContractProps = {
  contract: ImplementationContractData
  selectedItemId: string | null
  guidedStep: number
  inspectorOpen: boolean
  notice: ContractNotice
  resolutionPending?: boolean
  onSelectItem: (itemId: string) => void
  onOpenInspector: () => void
  onCloseInspector: () => void
  onGuidedNext: () => void
  onGuidedPrevious: () => void
  onOpenReader: (blockId: string) => void
  onResolve: (
    status: ContractResolutionStatus,
    resolvedValue: ContractValue | null,
    reason: string | null
  ) => void
  onRemainBlocked: () => void
  versions?: ImplementationContractVersion[]
  diff?: ImplementationContractDiff | null
  activationError?: string | null
  onSelectVersion?: (versionId: string) => void
  onCompareVersions?: (versionId: string, againstVersionId: string) => void
  onActivateVersion?: (versionId: string) => void
  onExport?: (
    format: ContractExportFormat,
    language: ContractExportLanguage
  ) => Promise<ImplementationContractExport>
  onOpenHistory?: () => void
  onOpenMapNode?: (nodeId: string) => void
}

export function ImplementationContract({
  contract,
  selectedItemId,
  guidedStep,
  inspectorOpen,
  notice,
  resolutionPending = false,
  onSelectItem,
  onOpenInspector,
  onCloseInspector,
  onGuidedNext,
  onGuidedPrevious,
  onOpenReader,
  onResolve,
  onRemainBlocked,
  versions = [],
  diff = null,
  activationError = null,
  onSelectVersion = () => undefined,
  onCompareVersions = () => undefined,
  onActivateVersion = () => undefined,
  onExport,
  onOpenHistory,
  onOpenMapNode
}: ImplementationContractProps) {
  const [workspaceView, setWorkspaceView] = useState<'review' | 'history' | 'export'>('review')
  const selectedItem =
    contract.items.find((item) => item.id === selectedItemId) ?? contract.items[0] ?? null
  const blockerCount = contract.issues.filter((issue) => issue.severity === 'error').length

  return (
    <section className="contract-shell" aria-label="Implementation Contract workspace">
      <header className="contract-statusbar">
        <div>
          <p className="kicker">Implementation Contract · schema {contract.schema_version}</p>
          <h2>Research-to-code handoff</h2>
        </div>
        <div
          className={`contract-readiness readiness-${contract.readiness}`}
          role="status"
          aria-label="Contract readiness"
        >
          {contract.readiness === 'implementation_ready' ? (
            <CircleCheck aria-hidden="true" size={18} />
          ) : (
            <ShieldAlert aria-hidden="true" size={18} />
          )}
          <strong>{contractReadinessLabel(contract.readiness)}</strong>
          <span>{blockerCount} blocking issue{blockerCount === 1 ? '' : 's'}</span>
        </div>
        <nav className="contract-surface-nav" aria-label="Contract surfaces">
          {workspaceView !== 'review' ? (
            <button type="button" onClick={() => setWorkspaceView('review')} aria-label="Return to Contract review">
              Review
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => {
              setWorkspaceView('history')
              onOpenHistory?.()
            }}
            aria-label="Open Contract history"
          >
            History
          </button>
          <button type="button" onClick={() => setWorkspaceView('export')} aria-label="Open Contract export">
            Export
          </button>
        </nav>
      </header>

      <div className="contract-trust-strip">
        {contract.status === 'partial' ? (
          <span className="warning-badge">
            <AlertTriangle aria-hidden="true" size={14} /> Partial contract
          </span>
        ) : null}
        {contract.is_stale ? (
          <p className="contract-stale-alert" role="alert">
            The source or Research Map changed. Rebuild before implementation.
          </p>
        ) : null}
      </div>

      {notice && !inspectorOpen ? (
        <p
          className={notice.kind === 'error' ? 'map-alert' : 'map-status'}
          role={notice.kind === 'error' ? 'alert' : 'status'}
        >
          {notice.message}
        </p>
      ) : null}

      {workspaceView === 'history' ? (
        <ContractVersions
          versions={versions}
          selectedVersionId={contract.id}
          diff={diff}
          activationError={activationError}
          onSelectVersion={onSelectVersion}
          onCompare={onCompareVersions}
          onActivate={onActivateVersion}
        />
      ) : workspaceView === 'export' && onExport ? (
        <ContractExport
          readiness={contract.readiness}
          blockerCount={blockerCount}
          onExport={onExport}
        />
      ) : workspaceView === 'export' ? (
        <section className="contract-export" aria-label="Contract export">
          <p>Export is unavailable.</p>
        </section>
      ) : (
        <div
          className={
            inspectorOpen ? 'contract-workbench' : 'contract-workbench inspector-collapsed'
          }
        >
        <nav className="contract-outline" aria-label="Implementation Contract outline">
          <div className="contract-outline-header">
            <span>{contract.items.length}</span>
            <small>typed implementation items</small>
          </div>
          {contractSectionDefinitions.map((section, sectionIndex) => {
            const items = contract.items.filter((item) => item.section === section.key)
            const sectionBlockers = items.filter((item) =>
              item.issues.some((issue) => issue.severity === 'error')
            ).length
            return (
              <section className="contract-outline-section" key={section.key}>
                <header>
                  <span aria-hidden="true">{String(sectionIndex + 1).padStart(2, '0')}</span>
                  <h3>{section.label}</h3>
                  <small>{items.length} item{items.length === 1 ? '' : 's'}</small>
                  {sectionBlockers ? (
                    <strong>{sectionBlockers} blocker{sectionBlockers === 1 ? '' : 's'}</strong>
                  ) : null}
                </header>
                {items.map((item) => (
                  <button
                    type="button"
                    className={item.id === selectedItem?.id ? 'contract-outline-item selected' : 'contract-outline-item'}
                    aria-label={contractItemTypeLabel(item.item_type)}
                    aria-current={item.id === selectedItem?.id ? 'true' : undefined}
                    data-origin={item.effective_origin}
                    onClick={() => onSelectItem(item.id)}
                    key={item.id}
                  >
                    <span>{contractItemTypeLabel(item.item_type)}</span>
                    <small>{contractOriginLabel(item.effective_origin)}</small>
                  </button>
                ))}
              </section>
            )
          })}
        </nav>

        <main className="contract-review-main">
          <ContractGuidedReview
            contract={contract}
            step={guidedStep}
            onPrevious={onGuidedPrevious}
            onNext={onGuidedNext}
            onInspectItem={(itemId) => {
              onSelectItem(itemId)
              onOpenInspector()
            }}
          />

          {selectedItem ? (
            <section
              className="contract-value-comparison"
              aria-label={`Draft and effective value for ${selectedItem.item_type.replaceAll('_', ' ')}`}
            >
              <header>
                <div>
                  <p className="field-label">Selected contract item</p>
                  <h2>{contractItemTypeLabel(selectedItem.item_type)}</h2>
                </div>
                {!inspectorOpen ? (
                  <button
                    type="button"
                    className="reader-link"
                    onClick={onOpenInspector}
                    aria-label="Inspect selected contract item"
                  >
                    <LocateFixed aria-hidden="true" size={16} /> Inspect evidence
                  </button>
                ) : null}
              </header>
              <div className="contract-value-grid">
                <div>
                  <span>Draft</span>
                  <strong>{contractValueLabel(selectedItem.draft_value)}</strong>
                </div>
                <div aria-hidden="true">→</div>
                <div>
                  <span>Effective</span>
                  <strong>{contractValueLabel(selectedItem.effective_value)}</strong>
                </div>
              </div>
            </section>
          ) : null}
        </main>

        {inspectorOpen && selectedItem ? (
          <ContractInspector
            item={selectedItem}
            pending={resolutionPending}
            notice={notice}
            onClose={onCloseInspector}
            onOpenReader={onOpenReader}
            onResolve={onResolve}
            onRemainBlocked={onRemainBlocked}
            onOpenMapNode={onOpenMapNode}
          />
        ) : null}
        </div>
      )}
    </section>
  )
}
