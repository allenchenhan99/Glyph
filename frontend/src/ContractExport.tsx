import { Download, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'

import type {
  ContractExportFormat,
  ContractExportLanguage,
  ContractReadiness,
  ImplementationContractExport
} from './types'

type ContractExportProps = {
  readiness: ContractReadiness
  blockerCount: number
  onExport: (
    format: ContractExportFormat,
    language: ContractExportLanguage
  ) => Promise<ImplementationContractExport>
}

type DownloadState = { href: string; filename: string } | null

export function ContractExport({
  readiness,
  blockerCount,
  onExport
}: ContractExportProps) {
  const [format, setFormat] = useState<ContractExportFormat>('json')
  const [language, setLanguage] = useState<ContractExportLanguage>('en')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [download, setDownload] = useState<DownloadState>(null)

  useEffect(
    () => () => {
      if (download) URL.revokeObjectURL(download.href)
    },
    [download]
  )

  async function downloadExport() {
    setPending(true)
    setError(null)
    try {
      const result = await onExport(format, language)
      if (download) URL.revokeObjectURL(download.href)
      const href = URL.createObjectURL(result.blob)
      setDownload({ href, filename: result.filename })
      const anchor = document.createElement('a')
      anchor.href = href
      anchor.download = result.filename
      anchor.click()
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Export unavailable.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="contract-export" aria-label="Contract export">
      <header>
        <Download aria-hidden="true" size={20} />
        <div>
          <p className="kicker">Deterministic handoff</p>
          <h2>Export contract</h2>
        </div>
      </header>

      {readiness !== 'implementation_ready' ? (
        <div className="contract-export-warning" role="alert">
          <ShieldAlert aria-hidden="true" size={18} />
          <div>
            <strong>NOT IMPLEMENTATION READY</strong>
            <span>{blockerCount} blocker{blockerCount === 1 ? '' : 's'} remain.</span>
          </div>
        </div>
      ) : (
        <p className="contract-export-boundary">
          This contract is structurally ready. Glyph does not validate profitability or guarantee
          investment performance.
        </p>
      )}

      <div className="contract-export-controls">
        <label>
          Export format
          <select value={format} onChange={(event) => setFormat(event.currentTarget.value as ContractExportFormat)}>
            <option value="json">Typed JSON</option>
            <option value="markdown">Markdown</option>
          </select>
        </label>
        <label>
          Export language
          <select value={language} onChange={(event) => setLanguage(event.currentTarget.value as ContractExportLanguage)}>
            <option value="en">English</option>
            <option value="zh-TW">繁體中文</option>
            <option value="bilingual">Bilingual</option>
          </select>
        </label>
        <button
          type="button"
          className="primary-action"
          disabled={pending}
          onClick={() => void downloadExport()}
          aria-label={error ? 'Retry contract export' : 'Download contract export'}
        >
          <Download aria-hidden="true" size={16} /> {pending ? 'Preparing…' : 'Download export'}
        </button>
      </div>

      {error ? <p className="map-alert" role="alert">{error}</p> : null}
      {download ? (
        <a href={download.href} download={download.filename}>
          Download {download.filename} again
        </a>
      ) : null}
    </section>
  )
}
