import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SettingsPage } from './pages/SettingsPage'
import { getAiSettings, updateAiSettings } from './api'

vi.mock('./api', () => ({ getAiSettings: vi.fn(), updateAiSettings: vi.fn() }))

beforeEach(() => {
  vi.mocked(getAiSettings).mockResolvedValue({ provider: 'claude_cli', model: '', has_api_key: false, ocr_mode: 'mock' })
})

it('lets the user select OrcaRouter, save their own key and clears the input', async () => {
  vi.mocked(updateAiSettings).mockResolvedValue({ provider: 'orcarouter', model: 'test/model', has_api_key: true, ocr_mode: 'mock' })
  const onApplied = vi.fn()
  render(<SettingsPage onApplied={onApplied} />)
  fireEvent.change(await screen.findByLabelText('Translation provider'), { target: { value: 'orcarouter' } })
  fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: 'test/model' } })
  fireEvent.change(screen.getByLabelText('OrcaRouter API key'), { target: { value: 'user-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Apply settings' }))
  await waitFor(() => expect(updateAiSettings).toHaveBeenCalledWith({ provider: 'orcarouter', model: 'test/model', api_key: 'user-secret' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Settings applied')
  expect(screen.getByLabelText('OrcaRouter API key')).toHaveValue('')
  expect(onApplied).toHaveBeenCalledOnce()
  expect(screen.getByRole('link', { name: 'Create an OrcaRouter account' })).toHaveAttribute('href', 'https://www.orcarouter.ai/ref/ref_790f54197e176818f92b')
})

it('shows save failures without claiming success', async () => {
  vi.mocked(updateAiSettings).mockRejectedValue(new Error('Service unavailable'))
  render(<SettingsPage />)
  await screen.findByLabelText('Translation provider')
  fireEvent.click(screen.getByRole('button', { name: 'Apply settings' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Service unavailable')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
