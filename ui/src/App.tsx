import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark-dimmed.css";

// Prefer the Vite proxy in dev (relative path) to avoid CORS; use env in prod/tests
function getBackendBase(): string {
  const viteEnv = (import.meta as unknown as { env?: { VITE_BACKEND_URL?: unknown; DEV?: boolean } }).env;
  const isDev = Boolean(viteEnv?.DEV);
  // If running in a browser and Vite dev server, use relative path so the proxy handles routing
  if (typeof window !== "undefined" && isDev) return "";

  const nodeEnv = (globalThis as unknown as { process?: { env?: { VITE_BACKEND_URL?: unknown } } }).process?.env;
  const candidate = viteEnv?.VITE_BACKEND_URL ?? nodeEnv?.VITE_BACKEND_URL;
  return typeof candidate === "string" ? candidate.replace(/\/$/, "") : "";
}
const BACKEND_URL = getBackendBase();
interface ChatEvent {
  name: string;
  data: unknown;
  at: number;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  events?: ChatEvent[];
}

function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: string }).name === "AbortError"
  );
}

function formatEventData(data: unknown): string {
  if (typeof data === "string") return data;
  if (data == null) return "";
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function summariseEvent(data: unknown): string {
  if (typeof data === "string") return data;
  if (data == null) return "";
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const raw = localStorage.getItem("chat_messages");
      const base = Date.now();
      return raw
        ? (JSON.parse(raw) as Message[]).map((m, i) => ({
            ...m,
            timestamp: m.timestamp ?? base + i * 1000,
            events: Array.isArray(m.events) ? m.events : [],
          }))
        : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    try {
      return (localStorage.getItem("theme") as "dark" | "light") || "dark";
    } catch {
      return "dark";
    }
  });
  const [controller, setController] = useState<AbortController | null>(null);
  const [latestEvent, setLatestEvent] = useState<string>("");
  const endRef = useRef<HTMLDivElement | null>(null);
  const saveTimeout = useRef<number | undefined>(undefined);
  const actionButtonClass = [
    "rounded-md",
    "px-4",
    "py-2",
    "text-white",
    "transition-colors",
    "disabled:opacity-50",
    loading
      ? "bg-red-600 hover:bg-red-500"
      : "bg-brand-600 hover:bg-brand-500",
  ].join(" ");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    if (messages.length === 0) return;
    window.clearTimeout(saveTimeout.current);
    saveTimeout.current = window.setTimeout(() => {
      try {
        localStorage.setItem("chat_messages", JSON.stringify(messages));
      } catch {
        /* ignore */
      }
    }, 300);
    return () => window.clearTimeout(saveTimeout.current);
  }, [messages]);

  async function send() {
    if (!input.trim() || loading) return;
    const text = input;
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", content: text, timestamp: Date.now() },
    ]);
    setLoading(true);
    setLatestEvent("");

    const aborter = new AbortController();
    setController(aborter);

    try {
      const url = BACKEND_URL ? `${BACKEND_URL}/chat?stream=events` : "/chat?stream=events";
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: aborter.signal,
      });
      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      let assistant = "";
      let buffer = "";
      const assistantTimestamp = Date.now();
      let assistantEvents: ChatEvent[] = [];

      const updateAssistant = (
        updater: (existing: Message | undefined) => Message,
        ensureCreate = false,
      ) => {
        setMessages((prev) => {
          const index = prev.findIndex(
            (msg) => msg.role === "assistant" && msg.timestamp === assistantTimestamp,
          );
          if (index === -1 && !ensureCreate) {
            return prev;
          }
          const updated = updater(index >= 0 ? prev[index] : undefined);
          const copy = [...prev];
          if (index >= 0) {
            copy[index] = updated;
          } else {
            copy.push(updated);
          }
          return copy;
        });
      };

      const processLine = (line: string) => {
        if (!line) return;
        try {
          const evt = JSON.parse(line) as { event?: string; data?: unknown };
          if (evt.event === "token") {
            const tok = typeof evt.data === "string" ? evt.data : "";
            if (!tok) return;
            assistant += tok;
            updateAssistant(
              () => ({
                role: "assistant",
                content: assistant,
                timestamp: assistantTimestamp,
                events: assistantEvents.map((item) => ({ ...item })),
              }),
              true,
            );
          } else {
            const name = typeof evt.event === "string" ? evt.event : "event";
            const newEvent: ChatEvent = {
              name,
              data: evt.data ?? null,
              at: Date.now(),
            };
            assistantEvents = [...assistantEvents, newEvent];
            const desc = summariseEvent(evt.data ?? null);
            setLatestEvent(`${name}: ${desc}`);
            updateAssistant((existing) => {
              const baseContent = existing?.content ?? assistant;
              return {
                role: "assistant",
                content: baseContent,
                timestamp: assistantTimestamp,
                events: assistantEvents.map((item) => ({ ...item })),
              };
            });
          }
        } catch {
          /* ignore malformed event */
        }
      };

      if (reader) {
        (aborter.signal as unknown as { addEventListener?: (type: string, cb: () => void) => void })
          .addEventListener?.("abort", () => {
            void reader.cancel();
          });
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buffer.indexOf("\n")) !== -1) {
            const line = buffer.slice(0, idx).trim();
            buffer = buffer.slice(idx + 1);
            processLine(line);
          }
        }
        const remainder = buffer.trim();
        if (remainder) {
          processLine(remainder);
        }
        if (assistantEvents.length || assistant) {
          updateAssistant(
            (existing) => ({
              role: "assistant",
              content: assistant || existing?.content || "",
              timestamp: assistantTimestamp,
              events: assistantEvents.map((item) => ({ ...item })),
            }),
            Boolean(assistantEvents.length || assistant),
          );
        }
      }
    } catch (e: unknown) {
      if (!isAbortError(e)) {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: "Error contacting server.",
            timestamp: Date.now(),
          },
        ]);
      }
    } finally {
      setLoading(false);
      setController(null);
      setLatestEvent("");
    }
  }

  function stop() {
    controller?.abort();
  }

  function CodeBlock({
    inline,
    className = "",
    children,
  }: {
    inline?: boolean;
    className?: string;
    children?: React.ReactNode;
  }) {
    const code = String(children ?? "");
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
    );
  }

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 flex flex-col">
      <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight">GenAI Chat</h1>
          <div className="flex items-center gap-2">
            <button
              className="rounded-md border px-2 py-1 text-sm border-slate-300 dark:border-slate-700"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? "Light" : "Dark"} mode
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl h-full flex flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
            {loading && latestEvent ? (
              <div className="flex justify-start">
                <span
                  aria-live="polite"
                  className="text-xs text-slate-500 bg-slate-100 dark:bg-slate-800 rounded px-2 py-1 animate-pulse"
                >
                  {latestEvent}
                </span>
              </div>
            ) : null}
            {messages.map((m, i) => (
              <div
                key={`${i}-${m.timestamp}`}
                className={m.role === "user" ? "text-right" : "text-left"}
              >
                {m.role === "user" ? (
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
                    {m.events?.length ? (
                      <details className="mt-3 space-y-2">
                        <summary className="text-xs font-medium text-slate-500 cursor-pointer">
                          Events ({m.events.length})
                        </summary>
                        <ul className="space-y-2 text-xs not-prose">
                          {m.events.map((evt) => (
                            <li
                              key={`${evt.at}-${evt.name}`}
                              className="rounded-md border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/60 p-2"
                            >
                              <div className="font-semibold text-slate-600 dark:text-slate-300">
                                {evt.name}
                              </div>
                              <pre className="mt-1 whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">
                                {formatEventData(evt.data)}
                              </pre>
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
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
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
            }}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Type your message..."
            disabled={loading}
          />
          <button
            type="button"
            className={actionButtonClass}
            onClick={loading ? stop : send}
            disabled={!loading && !input.trim()}
          >
            {loading ? "Stop" : "Send"}
          </button>
        </div>
      </footer>
    </div>
  );
}

export default App;
