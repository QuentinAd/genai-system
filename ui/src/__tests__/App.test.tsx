import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from '../App'

vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ body: undefined })) as unknown as typeof fetch)

describe('App', () => {
  it('renders and sends a message', async () => {
    render(<App />)
    const input = screen.getByPlaceholderText('Type your message...')
    await userEvent.type(input, 'Hello{enter}')
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })
})
