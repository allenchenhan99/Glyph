import { GitCompareArrows, History, ShieldAlert } from 'lucide-react'
import { useState } from 'react'

import type {
  ContractDiffClassification,
  ImplementationContractDiff,
  ImplementationContractVersion
} from './types'

type ContractVersionsProps = {
  versions: ImplementationContractVersion[]
  selectedVersionId: string
  diff: ImplementationContractDiff | null
  activationError: string | null
  onSelectVersion: (versionId: string) => void
  onCompare: (versionId: string, againstVersionId: string) => void
  onActivate: (versionId: string) => void
}

const diffGroups: ReadonlyArray<{
  classification: ContractDiffClassification
  label: string
}> = [
  { classification: 'value_changed', label: 'Value changed' },
  { classification: 'origin_changed', label: 'Origin changed' },
  { classification: 'evidence_changed', label: 'Evidence changed' },
  { classification: 'added', label: 'Added' },
  { classification: 'removed', label: 'Removed' },
  { classification: 'unchanged', label: 'Unchanged' }
]

export function ContractVersions({
  versions,
  selectedVersionId,
  diff,
  activationError,
  onSelectVersion,
  onCompare,
  onActivate
}: ContractVersionsProps) {
  const [confirmVersionId, setConfirmVersionId] = useState<string | null>(null)
  const compareCandidates = versions.filter((version) => version.id !== selectedVersionId)

  return (
    <section className="contract-versions" aria-label="Contract version history">
      <header>
        <History aria-hidden="true" size={20} />
        <div>
          <p className="kicker">Version history</p>
          <h2>Contract lineage</h2>
        </div>
      </header>

      {activationError ? (
        <p className="map-alert" role="alert">{activationError}</p>
      ) : null}

      <div className="contract-version-list">
        {versions.map((version) => (
          <article aria-label={`Contract version ${version.id}`} key={version.id}>
            <div className="contract-version-meta">
              <strong>{version.id}</strong>
              <span>{new Date(version.created_at).toLocaleString()}</span>
              <div className="claim-tags">
                {version.is_active ? <span className="reviewed-tag">Active</span> : null}
                {version.is_current ? <span>Current</span> : null}
                {version.is_stale ? <span className="warning-badge">Stale</span> : null}
                <span>{version.status}</span>
                <span>{version.readiness}</span>
              </div>
            </div>
            <div className="contract-version-actions">
              <button
                type="button"
                className="text-button"
                aria-pressed={version.id === selectedVersionId}
                onClick={() => onSelectVersion(version.id)}
              >
                View version
              </button>
              {!version.is_active ? (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setConfirmVersionId(version.id)}
                  aria-label={`Activate ${version.id}`}
                >
                  Activate
                </button>
              ) : null}
            </div>
            {confirmVersionId === version.id ? (
              <div className="contract-activation-confirm" role="group" aria-label={`Confirm activation for ${version.id}`}>
                <ShieldAlert aria-hidden="true" size={18} />
                <p>
                  Activating this history version does not make stale inputs current. It only
                  changes the active contract.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setConfirmVersionId(null)
                    onActivate(version.id)
                  }}
                  aria-label={`Confirm activation of ${version.id}`}
                >
                  Confirm activation
                </button>
                <button type="button" onClick={() => setConfirmVersionId(null)}>
                  Cancel
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>

      {compareCandidates.length ? (
        <label className="contract-compare-control">
          Compare selected version against
          <select
            key={selectedVersionId}
            defaultValue=""
            onChange={(event) => {
              if (event.currentTarget.value) {
                onCompare(selectedVersionId, event.currentTarget.value)
              }
            }}
          >
            <option value="" disabled>Select version</option>
            {compareCandidates.map((version) => (
              <option value={version.id} key={version.id}>{version.id}</option>
            ))}
          </select>
        </label>
      ) : null}

      {diff ? (
        <section className="contract-diff" aria-label="Contract version differences">
          <header>
            <GitCompareArrows aria-hidden="true" size={18} />
            <strong>{diff.version_id} against {diff.against_version_id}</strong>
          </header>
          {diffGroups.map((group) => {
            const items = diff.items.filter(
              (item) => item.classification === group.classification
            )
            return items.length ? (
              <section key={group.classification}>
                <h4>{group.label}</h4>
                <ul>
                  {items.map((item) => <li key={item.item_key}>{item.item_key}</li>)}
                </ul>
              </section>
            ) : null
          })}
        </section>
      ) : null}
    </section>
  )
}
