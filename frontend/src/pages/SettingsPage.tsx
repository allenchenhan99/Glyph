import { useEffect, useState, type FormEvent } from 'react'
import { getAiSettings, updateAiSettings, type AiProvider, type AiSettings } from '../api'
import '../styles/settings.css'
import type { WorkspaceStatus } from '../types'

export function SettingsPage({ onApplied, workspace }: { onApplied?: () => void; workspace?: WorkspaceStatus | null }) {
  const [settings, setSettings] = useState<AiSettings | null>(null)
  const [provider, setProvider] = useState<AiProvider>('claude_cli')
  const [model, setModel] = useState('')
  const [key, setKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    getAiSettings().then(value => {
      if (!active) return
      setSettings(value)
      setProvider(value.provider)
      setModel(value.model)
    }).catch(() => { if (active) setError('Could not load settings. Reopen Settings to try again.') })
    return () => { active = false }
  }, [])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await updateAiSettings({ provider, model: model.trim(), ...(key.trim() ? { api_key: key.trim() } : {}) })
      setSettings(updated)
      setKey('')
      onApplied?.()
      setMessage('Settings applied. New document runs use this provider; current runs keep their settings.')
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Could not apply settings.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="settings-page" aria-labelledby="settings-title">
      <header className="settings-header">
        <p className="settings-eyebrow">YOUR READING WORKSPACE</p>
        <h1 id="settings-title">Translation settings</h1>
        <p>Choose how Glyph translates your documents.</p>
      </header>
      {error && <p role="alert" className="settings-error">{error}</p>}
      {!settings && !error && <p>Loading settings…</p>}
      {settings && <form className="settings-card" onSubmit={save}>
        <fieldset disabled={saving}>
          <legend>Provider &amp; model</legend>
          <label htmlFor="ai-provider">Translation provider</label>
          <select id="ai-provider" value={provider} onChange={event => {
            const value = event.target.value
            if (value === 'claude_cli' || value === 'codex_cli' || value === 'orcarouter' || value === 'mock') {
              setProvider(value)
              setModel(value === settings.provider ? settings.model : '')
              setMessage('')
            }
          }}>
            <option value="claude_cli">Claude Code CLI</option>
            <option value="codex_cli">Codex CLI</option>
            <option value="orcarouter">OrcaRouter · your own API key</option>
            {settings.provider === 'mock' && <option value="mock">Mock · development only</option>}
          </select>
          <label htmlFor="ai-model">Model ID</label>
          <input id="ai-model" value={model} maxLength={200} required={provider === 'orcarouter'}
            placeholder={provider === 'orcarouter' ? 'Copy a model ID from the OrcaRouter catalog' : 'Leave blank for your CLI default'}
            onChange={event => setModel(event.target.value)} aria-describedby="model-help" />
          <p id="model-help" className="settings-help">{provider === 'orcarouter'
            ? 'Choose a text model with JSON output support. Check its price and limits before processing. Glyph does not add a fallback model.'
            : 'Uses your existing authenticated CLI. Glyph does not read or copy CLI credentials.'}</p>
          {provider === 'orcarouter' && <>
            <label htmlFor="ai-key">OrcaRouter API key</label>
            <input id="ai-key" type="password" autoComplete="off" spellCheck={false} value={key}
              required={!settings.has_api_key} maxLength={4096}
              placeholder={settings.has_api_key ? 'Key configured · leave blank to keep it' : 'Paste your own API key'}
              onChange={event => setKey(event.target.value)} aria-describedby="key-help" />
            <p id="key-help" className="settings-help">Keys entered here stay in backend memory for this session. Restarting Glyph clears these settings; environment configuration is used again.</p>
            <div className="settings-notice">
              <strong>Your account, your usage</strong>
              <p>Processing sends extracted document text to OrcaRouter and its model provider. API usage is billed to your OrcaRouter account. Set a spending limit there before translating large documents.</p>
              <div className="settings-links">
                <a href="https://www.orcarouter.ai/ref/ref_790f54197e176818f92b" target="_blank" rel="noopener noreferrer">Create an OrcaRouter account</a>
                <a href="https://www.orcarouter.ai/models" target="_blank" rel="noopener noreferrer">Browse models</a>
              </div>
              <p className="settings-help">Referral disclosure: Glyph may receive 5% of eligible referred usage. Using this link is optional.</p>
            </div>
          </>}
          <div className="settings-actions"><button type="submit">{saving ? 'Applying…' : 'Apply settings'}</button></div>
        </fieldset>
        {message && <p role="status" className="settings-success">{message}</p>}
      </form>}
      <aside className="settings-footnote">
        {workspace ? <>
          <h2>Summary and research provider: {workspace.research.provider}</h2>
          <p>{workspace.research.message}</p>
          <p>This provider is configured with GLYPH_AI_MODE in .env. Restart Glyph after changing it.</p>
        </> : null}
        <h2>Document processing</h2>
        <p>Successful translation batches are cached locally and reused when you retry with the same provider and model. Your last readable result remains available if reprocessing fails.</p>
        <p>Summaries, Research Maps and Implementation Contracts continue to use the provider configured in GLYPH_AI_MODE. These settings change document translation only. OCR is configured separately. Scanned PDFs and images still need your configured OCR provider; selecting OrcaRouter changes text translation only.</p>
      </aside>
    </section>
  )
}
