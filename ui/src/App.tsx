import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import MessageList from "./components/MessageList";
import MessageInput from "./components/MessageInput";

function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: string }).name === "AbortError"
  );
}

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; content: string }[]
  >(() => {
    try {
      const raw = localStorage.getItem("chat_messages");
      return raw
        ? (JSON.parse(raw) as { role: "user" | "assistant"; content: string }[])
        : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("theme") as "dark" | "light") || "dark",
  );
  const [controller, setController] = useState<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem("chat_messages", JSON.stringify(messages));
    } catch {
      /* ignore */
    }
  }, [messages]);

  const send = useCallback(async () => {
    if (!input.trim() || loading) return;
    const text = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);

    const aborter = new AbortController();
    setController(aborter);

    try {
      const resp = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: aborter.signal,
      });
      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      let assistant = "";
      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          assistant += decoder.decode(value, { stream: true });
          setMessages((m) => {
            const base = m;
            const lastIsAssistant = base[base.length - 1]?.role === "assistant";
            if (lastIsAssistant) {
              const copy = [...base];
              copy[copy.length - 1] = { role: "assistant", content: assistant };
              return copy;
            }
            return [...base, { role: "assistant", content: assistant }];
          });
        }
      }
    } catch (e: unknown) {
      if (!isAbortError(e)) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: "Error contacting server." },
        ]);
      }
    } finally {
      setLoading(false);
      setController(null);
    }
  }, [input, loading]);

  const stop = useCallback(() => {
    controller?.abort();
  }, [controller]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 flex flex-col">
      <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight">GenAI Chat</h1>
          <div className="flex items-center gap-2">
            {loading && (
              <span className="text-xs text-slate-500">Generating…</span>
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
              onClick={toggleTheme}
            >
              {theme === "dark" ? "Light" : "Dark"} mode
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl h-full flex flex-col">
          <MessageList messages={messages} endRef={endRef} />
        </div>
      </main>

      <footer className="sticky bottom-0 border-t border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl flex gap-2 items-end">
          <MessageInput
            input={input}
            setInput={setInput}
            send={send}
            loading={loading}
          />
        </div>
      </footer>
    </div>
  );
}

export default App;
