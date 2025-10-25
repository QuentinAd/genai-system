import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark-dimmed.css";

// Prefer the Vite proxy in dev (relative path) to avoid CORS; use env in prod/tests
function getBackendBase(): string {
  const viteEnv = (import.meta as unknown as { env?: { VITE_BACKEND_URL?: unknown; DEV?: boolean; MODE?: string } }).env;
  const nodeEnv = (globalThis as unknown as { process?: { env?: { VITE_BACKEND_URL?: unknown; NODE_ENV?: unknown } } }).process?.env;
  const mode = typeof viteEnv?.MODE === "string" ? viteEnv.MODE : (nodeEnv?.NODE_ENV as string | undefined);
  const isTest = mode === "test";
  const isDev = Boolean(viteEnv?.DEV) && !isTest;
  // If running in a browser and Vite dev server, use relative path so the proxy handles routing
  if (typeof window !== "undefined" && isDev) return "";

  const candidate = viteEnv?.VITE_BACKEND_URL ?? nodeEnv?.VITE_BACKEND_URL;
  return typeof candidate === "string" ? candidate.replace(/\/$/, "") : "";
}

const BACKEND_URL = getBackendBase();
const LOCAL_MESSAGES_KEY = "chat_messages";
const SESSION_STORAGE_KEY = "chat_session_id";

type RetrievalMode = "hirag" | "rag";

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
  mode?: RetrievalMode | null;
}

interface ConversationSummary {
  sessionId: string;
  updatedAt: number;
  preview: string;
  mode: RetrievalMode | null;
}

interface HistoryResponseShape {
  messages?: unknown[];
  items?: unknown[];
  history?: unknown[];
  next?: string | null;
  next_cursor?: string | null;
  cursor?: string | null;
}

function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: string }).name === "AbortError"
  );
}

function safeRandomId(): string {
  const cryptoLike = (globalThis as unknown as { crypto?: { randomUUID?: () => string; getRandomValues?: (arr: Uint8Array) => Uint8Array } }).crypto;
  if (cryptoLike?.randomUUID) return cryptoLike.randomUUID();
  return Math.random().toString(36).slice(2);
}

function parseTimestamp(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return parsed;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return fallback;
}

function normaliseMode(value: unknown): RetrievalMode | null {
  if (value === "hirag" || value === "rag") return value;
  if (typeof value !== "string") return null;
  const candidate = value.trim().toLowerCase();
  if (candidate === "hi" || candidate === "hirag") return "hirag";
  if (candidate === "naive" || candidate === "rag") return "rag";
  return null;
}

function truncatePreview(text: string, max = 80): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed || "Conversation";
  return `${trimmed.slice(0, max - 1)}…`;
}

function formatDisplayTime(timestamp: number): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function readStoredMode(): RetrievalMode | null {
  try {
    const raw = sessionStorage.getItem("chat_mode");
    return raw === "hirag" || raw === "rag" ? raw : null;
  } catch {
    return null;
  }
}

function loadStoredSession(): string {
  try {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY);
    if (stored) return stored;
  } catch {
    /* ignore */
  }
  return safeRandomId();
}

function loadStoredMessages(): Message[] {
  try {
    const raw = localStorage.getItem(LOCAL_MESSAGES_KEY);
    const base = Date.now();
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<Message>[];
    return parsed.map((m, i) => ({
      role: m?.role === "assistant" ? "assistant" : "user",
      content: typeof m?.content === "string" ? m.content : "",
      timestamp: m?.timestamp ?? base + i * 1000,
      events: Array.isArray(m?.events) ? m.events : [],
      mode: m?.mode === "hirag" || m?.mode === "rag" ? m.mode : null,
    }));
  } catch {
    return [];
  }
}

function normaliseConversation(raw: unknown): ConversationSummary | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const sessionIdCandidate = record.session_id ?? record.sessionId;
  if (typeof sessionIdCandidate !== "string" || !sessionIdCandidate.trim()) return null;
  const updatedAt = parseTimestamp(
    record.updated_at ?? record.updatedAt ?? record.last_timestamp ?? record.timestamp ?? Date.now(),
    Date.now(),
  );
  const previewSource: unknown[] = [
    record.preview,
    (record.last_message as Record<string, unknown> | undefined)?.content,
    (record.last_assistant_message as Record<string, unknown> | undefined)?.content,
    record.last_user_message,
    record.last_assistant_message,
  ];
  let preview = "";
  for (const candidate of previewSource) {
    if (typeof candidate === "string" && candidate.trim()) {
      preview = candidate.trim();
      break;
    }
  }
  const mode = normaliseMode(record.mode ?? record.last_mode ?? record.conversation_mode);
  return {
    sessionId: sessionIdCandidate,
    updatedAt,
    preview: truncatePreview(preview),
    mode,
  };
}

function normaliseHistoryMessages(raw: unknown[]): Message[] {
  const now = Date.now();
  const results: Message[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) continue;
    const record = entry as Record<string, unknown>;
    const role = record.role === "assistant" ? "assistant" : "user";
    const content = typeof record.content === "string" ? record.content : "";
    const timestamp = parseTimestamp(record.timestamp ?? record.at, now);
    const mode = normaliseMode(record.mode);
    let events: ChatEvent[] | undefined;
    if (Array.isArray(record.events)) {
      const processed: ChatEvent[] = [];
      for (const evt of record.events) {
        if (typeof evt !== "object" || evt === null) continue;
        const evtRecord = evt as Record<string, unknown>;
        const name = typeof evtRecord.name === "string" && evtRecord.name ? evtRecord.name : "event";
        const at = parseTimestamp(evtRecord.at ?? evtRecord.timestamp, timestamp);
        processed.push({ name, data: evtRecord.data ?? null, at });
      }
      events = processed;
    }
    results.push({ role, content, timestamp, events, mode });
  }
  results.sort((a, b) => a.timestamp - b.timestamp);
  return results;
}

function useDerivedActiveConversation(
  conversations: ConversationSummary[],
  sessionId: string,
): ConversationSummary | null {
  return useMemo(() => conversations.find((item) => item.sessionId === sessionId) ?? null, [conversations, sessionId]);
}

function resolveUrl(path: string): string {
  if (BACKEND_URL) return `${BACKEND_URL}${path}`;
  return path;
}

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>(() => loadStoredMessages());
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    try {
      return (localStorage.getItem("theme") as "dark" | "light") || "dark";
    } catch {
      return "dark";
    }
  });
  const [mode, setMode] = useState<RetrievalMode | null>(() => readStoredMode());
  const [controller, setController] = useState<AbortController | null>(null);
  const [latestEvent, setLatestEvent] = useState<string>("");
  const endRef = useRef<HTMLDivElement | null>(null);
  const saveTimeout = useRef<number | undefined>(undefined);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);
  const historyCursorRef = useRef<string | null>(null);
  const historyLoadingRef = useRef(false);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationCursor, setConversationCursor] = useState<string | null>(null);
  const conversationCursorRef = useRef<string | null>(null);
  const conversationsLoadingRef = useRef(false);
  const conversationListRef = useRef<HTMLDivElement | null>(null);
  const conversationSentinelRef = useRef<HTMLDivElement | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => (typeof window === "undefined" ? true : window.innerWidth >= 768));
  const [activeSessionId, setActiveSessionId] = useState<string>(() => loadStoredSession());
  const activeConversation = useDerivedActiveConversation(conversations, activeSessionId);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (!autoScrollRef.current) {
      autoScrollRef.current = true;
      return;
    }
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
    try {
      if (mode) sessionStorage.setItem("chat_mode", mode);
      else sessionStorage.removeItem("chat_mode");
    } catch {
      /* ignore */
    }
  }, [mode]);

  useEffect(() => {
    if (messages.length === 0) {
      try {
        localStorage.removeItem(LOCAL_MESSAGES_KEY);
      } catch {
        /* ignore */
      }
      return;
    }
    window.clearTimeout(saveTimeout.current);
    saveTimeout.current = window.setTimeout(() => {
      try {
        localStorage.setItem(LOCAL_MESSAGES_KEY, JSON.stringify(messages));
      } catch {
        /* ignore */
      }
    }, 300);
    return () => window.clearTimeout(saveTimeout.current);
  }, [messages]);

  useEffect(() => {
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, activeSessionId);
    } catch {
      /* ignore */
    }
  }, [activeSessionId]);

  const touchConversation = useCallback(
    (sessionId: string, preview: string, conversationMode: RetrievalMode | null, updatedAt?: number) => {
      if (!sessionId) return;
      setConversations((prev) => {
        const merged = new Map<string, ConversationSummary>();
        for (const entry of prev) {
          merged.set(entry.sessionId, entry);
        }
        const existing = merged.get(sessionId);
        const timestamp = Math.max(updatedAt ?? Date.now(), existing?.updatedAt ?? 0);
        const nextPreview = truncatePreview(preview || existing?.preview || "Conversation");
        merged.set(sessionId, {
          sessionId,
          updatedAt: timestamp,
          preview: nextPreview,
          mode: conversationMode ?? existing?.mode ?? null,
        });
        const list = Array.from(merged.values());
        list.sort((a, b) => b.updatedAt - a.updatedAt);
        return list;
      });
    },
    [],
  );

  const loadConversations = useCallback(
    async (cursorValue: string | null = null, replace = false) => {
      if (conversationsLoadingRef.current) return;
      conversationsLoadingRef.current = true;
      try {
        const query = cursorValue ? `?cursor=${encodeURIComponent(cursorValue)}` : "";
        const resp = await fetch(resolveUrl(`/chat_history${query}`));
        if (!resp.ok) {
          if (replace) setConversations([]);
          return;
        }
        const data = (await resp.json()) as { sessions?: unknown[]; items?: unknown[]; conversations?: unknown[] } & HistoryResponseShape;
        const sessions = Array.isArray(data.sessions)
          ? data.sessions
          : Array.isArray(data.items)
          ? data.items
          : Array.isArray(data.conversations)
          ? data.conversations
          : [];
        const normalised = sessions
          .map((item) => normaliseConversation(item))
          .filter((item): item is ConversationSummary => Boolean(item));
        setConversations((prev) => {
          const base = replace ? [] : prev;
          const merged = new Map<string, ConversationSummary>();
          for (const entry of base) {
            merged.set(entry.sessionId, entry);
          }
          for (const entry of normalised) {
            const existing = merged.get(entry.sessionId);
            const updatedAt = Math.max(entry.updatedAt, existing?.updatedAt ?? 0);
            merged.set(entry.sessionId, {
              sessionId: entry.sessionId,
              updatedAt,
              preview: entry.preview || existing?.preview || "Conversation",
              mode: entry.mode ?? existing?.mode ?? null,
            });
          }
          const list = Array.from(merged.values());
          list.sort((a, b) => b.updatedAt - a.updatedAt);
          return list;
        });
        const nextCursor =
          typeof data.next === "string"
            ? data.next
            : typeof data.next_cursor === "string"
            ? data.next_cursor
            : typeof data.cursor === "string"
            ? data.cursor
            : null;
        setConversationCursor(nextCursor);
        conversationCursorRef.current = nextCursor;
      } catch {
        if (replace) setConversations([]);
      } finally {
        conversationsLoadingRef.current = false;
      }
    },
    [],
  );

  useEffect(() => {
    void loadConversations(null, true);
  }, [loadConversations]);

  useEffect(() => {
    const sentinel = conversationSentinelRef.current;
    const container = conversationListRef.current;
    if (!sentinel || !container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting && conversationCursorRef.current) {
          void loadConversations(conversationCursorRef.current);
        }
      },
      { root: container, threshold: 0.5 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadConversations]);

  const loadConversationHistory = useCallback(
    async (sessionId: string, cursorValue: string | null = null, prepend = false) => {
      if (!sessionId) return;
      if (historyLoadingRef.current) return;
      historyLoadingRef.current = true;
      try {
        const query = cursorValue ? `?cursor=${encodeURIComponent(cursorValue)}` : "";
        const resp = await fetch(resolveUrl(`/chat_history/${sessionId}${query}`));
        if (!resp.ok) return;
        const data = (await resp.json()) as HistoryResponseShape;
        const items = Array.isArray(data.messages)
          ? data.messages
          : Array.isArray(data.items)
          ? data.items
          : Array.isArray(data.history)
          ? data.history
          : [];
        const historyMessages = normaliseHistoryMessages(items);
        const nextCursor =
          typeof data.next === "string"
            ? data.next
            : typeof data.next_cursor === "string"
            ? data.next_cursor
            : typeof data.cursor === "string"
            ? data.cursor
            : null;
        const container = messagesContainerRef.current;
        let previousHeight = 0;
        let previousTop = 0;
        if (prepend && container) {
          previousHeight = container.scrollHeight;
          previousTop = container.scrollTop;
        }
        if (prepend) autoScrollRef.current = false;
        setMessages((prev) => {
          if (!prepend) {
            if (historyMessages.length) {
              const last = historyMessages[historyMessages.length - 1];
              touchConversation(sessionId, last.content, last.mode ?? null, last.timestamp);
            }
            return historyMessages;
          }
          if (!historyMessages.length) return prev;
          const combined = [...historyMessages, ...prev];
          const seen = new Set<string>();
          const merged: Message[] = [];
          for (const msg of combined) {
            const key = `${msg.timestamp}:${msg.role}:${msg.content}`;
            if (!seen.has(key)) {
              seen.add(key);
              merged.push(msg);
            }
          }
          merged.sort((a, b) => a.timestamp - b.timestamp);
          return merged;
        });
        if (prepend && container) {
          requestAnimationFrame(() => {
            const diff = container.scrollHeight - previousHeight;
            container.scrollTop = previousTop + diff;
          });
        }
        historyCursorRef.current = nextCursor;
        setHistoryCursor(nextCursor);
      } catch {
        /* ignore */
      } finally {
        historyLoadingRef.current = false;
      }
    },
    [touchConversation],
  );

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const handleScroll = () => {
      if (container.scrollTop <= 32 && historyCursorRef.current) {
        void loadConversationHistory(activeSessionId, historyCursorRef.current, true);
      }
    };
    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, [activeSessionId, loadConversationHistory]);

  const handleSelectConversation = useCallback(
    async (sessionId: string) => {
      if (!sessionId) return;
      setActiveSessionId(sessionId);
      historyCursorRef.current = null;
      setHistoryCursor(null);
      await loadConversationHistory(sessionId, null, false);
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        setSidebarOpen(false);
      }
    },
    [loadConversationHistory],
  );

  const handleNewConversation = useCallback(() => {
    const newId = safeRandomId();
    setActiveSessionId(newId);
    setMessages([]);
    historyCursorRef.current = null;
    setHistoryCursor(null);
    setSidebarOpen(false);
    try {
      localStorage.removeItem(LOCAL_MESSAGES_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const handleClearHistory = useCallback(async () => {
    if (!activeConversation) return;
    if (!window.confirm("Clear this conversation?")) return;
    try {
      const resp = await fetch(resolveUrl(`/chat_history/${activeConversation.sessionId}`), {
        method: "DELETE",
      });
      if (!resp.ok && resp.status !== 204) return;
    } catch {
      return;
    }
    setConversations((prev) => prev.filter((item) => item.sessionId !== activeConversation.sessionId));
    setMessages([]);
    historyCursorRef.current = null;
    setHistoryCursor(null);
    const newId = safeRandomId();
    setActiveSessionId(newId);
    try {
      localStorage.removeItem(LOCAL_MESSAGES_KEY);
    } catch {
      /* ignore */
    }
    void loadConversations(null, true);
  }, [activeConversation, loadConversations]);

  const send = useCallback(async () => {
    if (!input.trim() || loading) return;
    const text = input;
    const selectedMode = mode;
    setInput("");
    const sessionId = activeSessionId || safeRandomId();
    if (!activeSessionId) setActiveSessionId(sessionId);
    const timestamp = Date.now();
    const userMessage: Message = { role: "user", content: text, timestamp, mode: selectedMode };
    setMessages((m) => [...m, userMessage]);
    touchConversation(sessionId, text, selectedMode, timestamp);
    setLoading(true);
    setLatestEvent("");

    const aborter = new AbortController();
    setController(aborter);

    try {
      let url = `${resolveUrl("/chat")}?stream=events`;
      if (selectedMode === "hirag") url += "&hirag";
      else if (selectedMode === "rag") url += "&rag";
      const headers: HeadersInit = { "Content-Type": "application/json" };
      if (sessionId) headers["Session-Id"] = sessionId;
      const resp = await fetch(url, {
        method: "POST",
        headers,
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
        touchConversation(sessionId, assistant || text, selectedMode, Date.now());
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
                mode: selectedMode,
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
                mode: selectedMode ?? existing?.mode ?? null,
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
          let idx = buffer.indexOf("\n");
          while (idx !== -1) {
            const line = buffer.slice(0, idx).trim();
            buffer = buffer.slice(idx + 1);
            processLine(line);
            idx = buffer.indexOf("\n");
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
              mode: selectedMode ?? existing?.mode ?? null,
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
            mode: mode ?? null,
          },
        ]);
      }
    } finally {
      setLoading(false);
      setController(null);
      setLatestEvent("");
      void loadConversations(null, true);
    }
  }, [activeSessionId, input, loadConversations, loading, mode, touchConversation]);

  const stop = useCallback(() => {
    controller?.abort();
  }, [controller]);

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

  const toggleClass = (target: RetrievalMode) =>
    `rounded-md border px-3 py-1 text-xs font-medium transition-colors ${
      mode === target
        ? "bg-brand-600 border-brand-600 text-white"
        : "bg-white dark:bg-slate-900 border-slate-300 text-slate-600 hover:border-brand-500 dark:border-slate-700 dark:text-slate-300"
    }`;

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 flex flex-col">
      <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
        <div className="mx-auto w-full max-w-6xl flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-md border border-slate-300 dark:border-slate-700 px-2 py-1 text-sm"
              onClick={() => setSidebarOpen((open) => !open)}
              aria-pressed={sidebarOpen}
              aria-label="Toggle conversations panel"
            >
              {sidebarOpen ? "Hide" : "Show"}
            </button>
            <h1 className="text-lg font-semibold tracking-tight">GenAI Chat</h1>
          </div>
          <div className="flex items-center gap-2">
            {loading && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Generating…</span>
                {latestEvent ? (
                  <span
                    aria-live="polite"
                    className="text-xs text-slate-500 bg-slate-100 dark:bg-slate-800 rounded px-2 py-1 animate-pulse"
                    title={latestEvent}
                  >
                    {latestEvent}
                  </span>
                ) : null}
              </div>
            )}
            {loading ? (
              <button
                className="rounded-md border px-2 py-1 text-sm border-red-600 text-red-600"
                onClick={stop}
              >
                Stop
              </button>
            ) : null}
            <button
              className="rounded-md border px-2 py-1 text-sm border-slate-300 dark:border-slate-700"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? "Light" : "Dark"} mode
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <div className="mx-auto w-full max-w-6xl h-full flex">
          {sidebarOpen ? (
            <aside
              role="complementary"
              aria-label="Conversations"
              className="hidden sm:flex w-72 flex-col border-r border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/50"
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-300">Conversations</h2>
                <button
                  type="button"
                  className="rounded-md border px-2 py-1 text-xs border-slate-300 dark:border-slate-700"
                  onClick={handleNewConversation}
                >
                  New chat
                </button>
              </div>
              <div ref={conversationListRef} className="flex-1 overflow-y-auto">
                {conversations.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-slate-500">No conversations yet.</p>
                ) : null}
                <div className="px-2 py-2 space-y-1">
                  {conversations.map((conv) => {
                    const active = conv.sessionId === activeSessionId;
                    return (
                      <button
                        key={conv.sessionId}
                        type="button"
                        onClick={() => handleSelectConversation(conv.sessionId)}
                        className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                          active
                            ? "bg-brand-600 text-white shadow"
                            : "bg-white dark:bg-slate-900/60 text-slate-700 dark:text-slate-200 border border-transparent hover:border-brand-500"
                        }`}
                        aria-current={active ? "true" : undefined}
                        aria-label={`${conv.preview} • ${formatDisplayTime(conv.updatedAt)}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-medium line-clamp-1">{conv.preview}</span>
                          <span className="text-xs opacity-80">{formatDisplayTime(conv.updatedAt)}</span>
                        </div>
                        <div className="mt-1 text-xs opacity-80 uppercase tracking-wide">
                          {conv.mode === "hirag" ? "HiRAG" : conv.mode === "rag" ? "RAG" : "LLM"}
                        </div>
                      </button>
                    );
                  })}
                </div>
                <div ref={conversationSentinelRef} className="h-4" />
              </div>
            </aside>
          ) : null}

          <div className="flex-1 flex flex-col">
            <div className="flex items-center justify-between px-4 pt-4">
              <div>
                {activeConversation ? (
                  <div className="text-xs uppercase text-slate-500 dark:text-slate-400">
                    Viewing session {activeConversation.sessionId}
                  </div>
                ) : (
                  <div className="text-xs uppercase text-slate-500 dark:text-slate-400">
                    Draft conversation
                  </div>
                )}
              </div>
              {activeConversation ? (
                <button
                  type="button"
                  className="rounded-md border border-red-600 text-red-600 px-2 py-1 text-xs"
                  onClick={handleClearHistory}
                >
                  Clear history
                </button>
              ) : null}
            </div>
            <div
              ref={messagesContainerRef}
              data-testid="message-list"
              className="flex-1 overflow-y-auto px-4 py-6 space-y-3"
            >
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
                      {m.mode ? (
                        <span className="mt-3 inline-flex items-center rounded-full border border-brand-600/60 bg-brand-600/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-700 dark:text-brand-300">
                          {m.mode === "hirag" ? "HiRAG" : "RAG"} mode
                        </span>
                      ) : null}
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

            <footer className="sticky bottom-0 border-t border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
              <div className="w-full flex gap-2 items-end">
                <div className="flex-1 flex flex-col gap-2">
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
                        void send();
                      }
                    }}
                    placeholder="Type your message..."
                    disabled={loading}
                  />
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <span className="font-medium text-slate-600 dark:text-slate-300">Retrieval mode</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className={toggleClass("hirag")}
                        aria-label="Enable HiRAG retrieval"
                        aria-pressed={mode === "hirag"}
                        title="HiRAG: hierarchical retrieval for richer answers"
                        onClick={() => setMode((prev) => (prev === "hirag" ? null : "hirag"))}
                      >
                        HiRAG
                      </button>
                      <button
                        type="button"
                        className={toggleClass("rag")}
                        aria-label="Enable RAG retrieval"
                        aria-pressed={mode === "rag"}
                        title="RAG: standard retrieval-augmented responses"
                        onClick={() => setMode((prev) => (prev === "rag" ? null : "rag"))}
                      >
                        RAG
                      </button>
                    </div>
                  </div>
                </div>
                <button
                  className="rounded-md bg-brand-600 hover:bg-brand-500 disabled:opacity-50 px-4 py-2 text-white"
                  onClick={() => void send()}
                  disabled={loading || !input.trim()}
                >
                  Send
                </button>
              </div>
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
