import { render, screen, act, within } from '@testing-library/react'
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
    await userEvent.click(screen.getByText('Send'))
    const stopButton = await screen.findByRole('button', { name: 'Stop' })
    expect(stopButton.className).toContain('bg-red-600')
    expect(stopButton.className).toContain('hover:bg-red-500')
    const summary = await screen.findByText('> Events')
    expect(summary.tagName).toBe('SUMMARY')
    expect(summary.className).not.toContain('animate-fade-cycle')
    expect(fetch).toHaveBeenCalledWith('/chat?stream=events', expect.any(Object))
    await userEvent.click(stopButton)
    expect(cancel).toHaveBeenCalled()
  })

  it('updates assistant message with token events from NDJSON stream', async () => {
    const encoder = new TextEncoder()
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c
        // send a start event line, then two token lines
        c.enqueue(encoder.encode('{"event":"on_chat_model_start","data":{"input":"Hello"}}\n'))
        c.enqueue(encoder.encode('{"event":"token","data":"Hi"}\n'))
      },
    })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ body: stream })) as unknown as typeof fetch)

    render(<App />)
    const input = screen.getByPlaceholderText('Type your message...')
    await userEvent.type(input, 'Hello{enter}', { delay: 0 })
    const main = screen.getByRole('main')
    const summary = await within(main).findByText(/^> on_chat_model_start$/)
    expect(summary.tagName).toBe('SUMMARY')
    expect(summary.className).toContain('animate-fade-cycle')
    const details = summary.parentElement as HTMLDetailsElement | null
    expect(details?.open).toBe(false)
    const bubble = details?.nextElementSibling as HTMLElement | null
    if (!bubble) {
      throw new Error('Expected assistant bubble to be present')
    }
    await screen.findByText('Hi')
    await act(async () => {
      controller.enqueue(encoder.encode('{"event":"token","data":" there"}\n'))
      controller.enqueue(encoder.encode('{"event":"on_chat_model_end","data":{"output":"Hithere"}}\n'))
      controller.close()
    })
    await within(bubble).findByText('Hi there')
    const summaryAfter = await within(main).findByText(/^> on_chat_model_end$/)
    expect(summaryAfter).toBe(summary)
    expect(summaryAfter.className).toContain('animate-fade-cycle')
    const eventsTrigger = summaryAfter
    await userEvent.click(eventsTrigger)
    const openDetails = summaryAfter.parentElement as HTMLDetailsElement | null
    expect(openDetails?.open).toBe(true)
    if (!openDetails) {
      throw new Error('Expected details to be present')
    }
    await within(openDetails).findByText('on_chat_model_start')
    await within(openDetails).findByText(/"input"\s*:\s*"Hello"/)
    await within(openDetails).findByText('on_chat_model_end')
    await within(main).findByText('> Events', undefined, { timeout: 4000 })
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
