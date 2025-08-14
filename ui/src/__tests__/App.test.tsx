import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

// Provide a backend URL for tests before importing the app
process.env.VITE_BACKEND_URL = 'http://example.com'
const App = (await import('../App')).default

const cancel = vi.fn()
const read = vi.fn(() => new Promise<IteratorResult<Uint8Array>>(() => {}))

vi.stubGlobal(
  'fetch',
  vi.fn(() =>
    Promise.resolve({
      body: {
        getReader: () => ({ read, cancel }),
      },
    }),
  ) as unknown as typeof fetch,
)

describe('App', () => {
  it('uses backend URL and cancels on stop', async () => {
    render(<App />)
    const input = screen.getByPlaceholderText('Type your message...')
    await userEvent.type(input, 'Hello')
    userEvent.click(screen.getByText('Send'))
    await screen.findByText('Stop')
    expect(fetch).toHaveBeenCalledWith('http://example.com/chat', expect.any(Object))
    await userEvent.click(screen.getByText('Stop'))
    expect(cancel).toHaveBeenCalled()
  })
})
