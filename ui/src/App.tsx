import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark-dimmed.css'
import './App.css'

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'name' in err &&
    (err as { name?: string }).name === 'AbortError'
  )
}

// Simple icons
function ChatIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
      <path strokeWidth="2" d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 5V5Z" />
    </svg>
  )
}
function AgentIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
      <circle cx="12" cy="4" r="2" strokeWidth="2" />
      <path strokeWidth="2" d="M6 10h12M6 14h12M6 18h12" />
    </svg>
  )
}

export type Mode = 'chat' | 'agent'

type AgentEvent =
  | { type: 'tool_start'; name?: string; input?: unknown }
  | { type: 'tool_end'; name?: string; output?: unknown }

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>(() => {
    try {
      const raw = localStorage.getItem('chat_messages')
      return raw ? (JSON.parse(raw) as { role: 'user' | 'assistant'; content: string }[]) : []
    } catch {
      return []
    }
  })
  const [loading, setLoading] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('theme') as 'dark' | 'light') || 'dark')
  const [controller, setController] = useState<AbortController | null>(null)
  const [mode, setMode] = useState<Mode>(() => (localStorage.getItem('mode') as Mode) || 'chat')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activity, setActivity] = useState<AgentEvent[]>([])
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    try {
      localStorage.setItem('chat_messages', JSON.stringify(messages))
    } catch {
      /* ignore */
    }
  }, [messages])

  useEffect(() => {
    localStorage.setItem('mode', mode)
  }, [mode])

  async function send() {
    if (!input.trim() || loading) return
    const text = input
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    if (mode === 'agent') setActivity([])
    setLoading(true)

    const aborter = new AbortController()
    setController(aborter)

    try {
      if (mode === 'chat') {
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
                copy[copy.length - 1] = { role: 'assistant', content: assistant }
                return copy
              }
              return [...base, { role: 'assistant', content: assistant }]
            })
          }
        }
      } else {
        // Agent mode: NDJSON event stream
        const resp = await fetch('/agent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }),
          signal: aborter.signal,
        })
        const reader = resp.body?.getReader()
        const decoder = new TextDecoder()
        let assistant = ''
        let buffer = ''
        if (reader) {
          while (true) {
            const { value, done } = await reader.read()
            if (done) {
              // flush any trailing line
              if (buffer.trim()) handleAgentLine(buffer)
              break
            }
            const chunk = decoder.decode(value, { stream: true })
            buffer += chunk
            let idx: number
            // process by lines
            while ((idx = buffer.indexOf('\n')) !== -1) {
              const line = buffer.slice(0, idx)
              buffer = buffer.slice(idx + 1)
              const evt = handleAgentLine(line)
              if (evt?.type === 'token') {
                assistant += evt.content
                setMessages((m) => {
                  const base = m
                  const lastIsAssistant = base[base.length - 1]?.role === 'assistant'
                  if (lastIsAssistant) {
                    const copy = [...base]
                    copy[copy.length - 1] = { role: 'assistant', content: assistant }
                    return copy
                  }
                  return [...base, { role: 'assistant', content: assistant }]
                })
              }
            }
          }
        }
      }
    } catch (e: unknown) {
      if (!isAbortError(e)) {
        setMessages((m) => [...m, { role: 'assistant', content: 'Error contacting server.' }])
      }
    } finally {
      setLoading(false)
      setController(null)
    }
  }

  function handleAgentLine(line: string): any | null {
    const trimmed = line.trim()
    if (!trimmed) return null
    try {
      const evt = JSON.parse(trimmed)
      if (evt.type === 'tool_start') {
        setActivity((a) => [...a, { type: 'tool_start', name: evt.name, input: evt.input }])
      } else if (evt.type === 'tool_end') {
        setActivity((a) => [...a, { type: 'tool_end', name: evt.name, output: evt.output }])
      }
      return evt
    } catch {
      return null
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
      <div className="code-block">
        <button
          type="button"
          className="copy-btn"
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

  // New Chevron icon for collapse/expand
  function ChevronIcon({ open }: { open: boolean }) {
    return (
      <svg
        viewBox="0 0 24 24"
        className={`w-5 h-5 transition-transform ${open ? '' : 'rotate-180'}`}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="M9 18l6-6-6-6" />
      </svg>
    )
  }

  return (
    <div className="h-dvh overflow-hidden bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 flex">
      {/* Sidebar */}
      <aside
        className={`flex-shrink-0 overflow-hidden border-r border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/40 backdrop-blur transition-all duration-200 ${sidebarOpen ? 'w-56' : 'w-14'
          } flex flex-col text-slate-700 dark:text-slate-200`}
      >
        <button
          className="p-2 bg-transparent border-0 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen((v) => !v)}
        >
          <ChevronIcon open={sidebarOpen} />
        </button>
        <nav className="flex-1 px-2 py-2 space-y-1">
          <button
            className={`w-full flex items-center ${sidebarOpen ? 'justify-start' : 'justify-center'} gap-2 px-2 py-2 rounded-md text-left bg-transparent border-0 ${mode === 'chat' ? 'bg-brand-600 text-white' : 'hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            onClick={() => setMode('chat')}
          >
            <ChatIcon className="w-5 h-5" />
            {sidebarOpen ? <span>Chat</span> : null}
          </button>
          <button
            className={`w-full flex items-center ${sidebarOpen ? 'justify-start' : 'justify-center'} gap-2 px-2 py-2 rounded-md text-left bg-transparent border-0 ${mode === 'agent' ? 'bg-brand-600 text-white' : 'hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            onClick={() => setMode('agent')}
          >
            <AgentIcon className="w-5 h-5" />
            {sidebarOpen ? <span>Agent</span> : null}
          </button>
        </nav>
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-h-0">
        <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
          <div className="mx-auto w-full max-w-3xl flex items-center justify-between">
            <h1 className="text-lg font-semibold tracking-tight">GenAI {mode === 'agent' ? 'Agent' : 'Chat'}</h1>
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

        <main className="flex-1 min-h-0">
          <div className="mx-auto w-full max-w-3xl h-full flex flex-col min-h-0">
            <div className="flex-1 overflow-y-auto no-scrollbar px-4 py-6 space-y-3">
              {messages.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
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

              {mode === 'agent' && activity.length > 0 && (
                <div className="mt-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/40 p-3">
                  <div className="text-xs font-semibold mb-2 text-slate-600 dark:text-slate-300">Agent Activity</div>
                  <ul className="space-y-1 text-xs">
                    {activity.map((evt, idx) => (
                      <li key={idx} className="flex gap-2">
                        <span className="text-slate-500">{evt.type === 'tool_start' ? '▶' : '✓'}</span>
                        <span className="truncate">
                          {evt.type === 'tool_start' ? (
                            <>
                              <strong>{evt.name || 'tool'}</strong> started {evt.input ? `with ${JSON.stringify(evt.input)}` : ''}
                            </>
                          ) : (
                            <>
                              <strong>{evt.name || 'tool'}</strong> finished {evt.output ? `→ ${JSON.stringify(evt.output)}` : ''}
                            </>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </main>

        <footer className="sticky bottom-0 border-t border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
          <div className="mx-auto w-full max-w-3xl flex gap-2 items-end">
            <textarea
              className="flex-1 rounded-md no-scrollbar bg-white border border-slate-300 px-3 py-2 outline-none focus:ring-2 focus:ring-brand-500 placeholder:text-slate-500 dark:bg-slate-900 dark:border-slate-800 resize-none"
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
              placeholder={`Type your ${mode === 'agent' ? 'instruction' : 'message'}...`}
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
    </div>
  )
}

export default App
