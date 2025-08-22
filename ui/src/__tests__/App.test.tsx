import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

// Provide a backend URL for tests before importing the app
vi.stubGlobal('__APP_BACKEND_URL', 'http://example.com')
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
    await userEvent.click(screen.getByText('Send'))
    await screen.findByText('Stop')
    expect(fetch).toHaveBeenCalledWith('http://example.com/chat', expect.any(Object))
    await userEvent.click(screen.getByText('Stop'))
    expect(cancel).toHaveBeenCalled()
  })

  it('updates assistant message as stream arrives', async () => {
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c
        c.enqueue(encoder.encode('Hi'))
      },
    })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ body: stream })) as unknown as typeof fetch)

    render(<App />)
    const input = screen.getByPlaceholderText('Type your message...')
    await userEvent.type(input, 'Hello{enter}')
    await screen.findByText('Hi')
    await act(async () => {
      controller.enqueue(encoder.encode(' there'))
      controller.close()
    })
    await screen.findByText('Hi there')
  })

  it('stop button aborts the request', async () => {
    const abortSpy = vi.fn()
    const MockAbortController = class {
      signal = {}
      abort = abortSpy
    }
    vi.stubGlobal(
      'AbortController',
      MockAbortController as unknown as typeof AbortController,
    )

    const stream = new ReadableStream<Uint8Array>({
      start() {
        /* keep open */
      },
    })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ body: stream })) as unknown as typeof fetch)

    render(<App />)
    const input = screen.getByPlaceholderText('Type your message...')
    await userEvent.type(input, 'Hello{enter}')
    const stopBtn = await screen.findByText('Stop')
    await userEvent.click(stopBtn)
    expect(abortSpy).toHaveBeenCalled()
  })

  it('theme toggler switches classes and localStorage', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ body: undefined })) as unknown as typeof fetch)

    render(<App />)
    const button = screen.getByRole('button', { name: /mode/i })
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem('theme')).toBe('dark')

    await userEvent.click(button)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(localStorage.getItem('theme')).toBe('light')

    await userEvent.click(button)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})
