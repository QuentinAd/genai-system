import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from '../App'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  document.documentElement.className = ''
})

describe('App', () => {
  it('renders and sends a message', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ body: undefined })) as unknown as typeof fetch)
    render(<App />)
    const input = screen.getByPlaceholderText('Type your message...')
    await userEvent.type(input, 'Hello{enter}')
    expect(screen.getByText('Hello')).toBeInTheDocument()
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
