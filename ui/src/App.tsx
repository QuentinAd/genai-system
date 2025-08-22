import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark-dimmed.css'

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'name' in err &&
    (err as { name?: string }).name === 'AbortError'
  )
}

function App() {
  interface Message {
    role: 'user' | 'assistant'
    content: string
    timestamp: number
  }
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const raw = localStorage.getItem('chat_messages')
      return raw
        ? (JSON.parse(raw) as Message[]).map((m, i) => ({
            ...m,
            timestamp: m.timestamp ?? Date.now() + i,
          }))
        : []
    } catch {
      return []
    }
  })
  const [loading, setLoading] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try {
      return (localStorage.getItem('theme') as 'dark' | 'light') || 'dark'
    } catch {
      return 'dark'
    }
  })
  const [controller, setController] = useState<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const saveTimeout = useRef<number | undefined>(undefined)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])

  useEffect(() => {
    if (messages.length === 0) return
    window.clearTimeout(saveTimeout.current)
    saveTimeout.current = window.setTimeout(() => {
      try {
        localStorage.setItem('chat_messages', JSON.stringify(messages))
      } catch {
        /* ignore */
      }
    }, 300)
    return () => window.clearTimeout(saveTimeout.current)
  }, [messages])

  async function send() {
    if (!input.trim() || loading) return
    const text = input
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text, timestamp: Date.now() }])
    setLoading(true)

    const aborter = new AbortController()
    setController(aborter)

    try {
      const resp = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: aborter.signal,
      })
      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()
      let assistant = ''
      if (reader) {
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          assistant += decoder.decode(value, { stream: true })
          setMessages((m) => {
            const base = m
            const lastIsAssistant = base[base.length - 1]?.role === 'assistant'
            if (lastIsAssistant) {
              const copy = [...base]
              const last = copy[copy.length - 1]
              copy[copy.length - 1] = { ...last, content: assistant }
              return copy
            }
            return [
              ...base,
              { role: 'assistant', content: assistant, timestamp: Date.now() },
            ]
          })
        }
      }
    } catch (e: unknown) {
      if (!isAbortError(e)) {
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            content: 'Error contacting server.',
            timestamp: Date.now(),
          },
        ])
      }
    } finally {
      setLoading(false)
      setController(null)
    }
  }

  function stop() {
    controller?.abort()
  }

  function CodeBlock({ inline, className = '', children }: { inline?: boolean; className?: string; children?: React.ReactNode }) {
    const code = String(children ?? '')
    return inline ? (
      <code className={className}>{children}</code>
    ) : (
      <div className="relative">
        <button
          type="button"
          className="absolute top-2 right-2 bg-slate-950/70 text-white border border-slate-700 px-2 py-1 rounded text-xs hover:bg-slate-950/90 dark:bg-slate-800/70 dark:hover:bg-slate-800/90"
          onClick={() => navigator.clipboard.writeText(code)}
          aria-label="Copy code"
        >
          Copy
        </button>
        <pre className={className}>
          <code>{code}</code>
        </pre>
      </div>
    )
  }

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 flex flex-col">
      <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight">GenAI Chat</h1>
          <div className="flex items-center gap-2">
            {loading && <span className="text-xs text-slate-500">Generating…</span>}
            {loading ? (
              <button className="rounded-md border px-2 py-1 text-sm border-red-600 text-red-600" onClick={stop}>
                Stop
              </button>
            ) : null}
            <button
              className="rounded-md border px-2 py-1 text-sm border-slate-300 dark:border-slate-700"
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            >
              {theme === 'dark' ? 'Light' : 'Dark'} mode
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl h-full flex flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
            {messages.map((m, i) => (
              <div key={`${i}-${m.timestamp}`} className={m.role === 'user' ? 'text-right' : 'text-left'}>
                {m.role === 'user' ? (
                  <span className="inline-block rounded-2xl px-3 py-2 max-w-[80%] break-words shadow-sm bg-brand-600 text-white">
                    {m.content}
                  </span>
                ) : (
                  <div className="inline-block rounded-2xl px-3 py-2 max-w-[80%] break-words shadow-sm bg-slate-100 text-slate-900 ring-1 ring-slate-200 dark:bg-slate-800/80 dark:text-slate-100 dark:ring-slate-800 prose prose-slate dark:prose-invert prose-sm prose-pre:bg-slate-900 prose-pre:text-slate-100">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkBreaks]}
                      rehypePlugins={[rehypeHighlight]}
                      components={{ code: CodeBlock }}
                    >
                      {m.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            ))}
            <div ref={endRef} />
          </div>
        </div>
      </main>

      <footer className="sticky bottom-0 border-t border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl flex gap-2 items-end">
          <textarea
            className="flex-1 rounded-md bg-white border border-slate-300 px-3 py-2 outline-none focus:ring-2 focus:ring-brand-500 placeholder:text-slate-500 dark:bg-slate-900 dark:border-slate-800 resize-none"
            value={input}
            rows={1}
            onInput={(e) => {
              const el = e.currentTarget
              el.style.height = 'auto'
              el.style.height = `${Math.min(el.scrollHeight, 200)}px`
            }}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder="Type your message..."
            disabled={loading}
          />
          <button
            className="rounded-md bg-brand-600 hover:bg-brand-500 disabled:opacity-50 px-4 py-2 text-white"
            onClick={send}
            disabled={loading || !input.trim()}
          >
            Send
          </button>
        </div>
      </footer>
    </div>
  )
}

export default App
