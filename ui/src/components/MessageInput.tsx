import React from "react";

interface MessageInputProps {
  input: string;
  setInput: (value: string) => void;
  send: () => void;
  loading: boolean;
}

export default function MessageInput({
  input,
  setInput,
  send,
  loading,
}: MessageInputProps) {
  return (
    <>
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
        className="rounded-md bg-brand-600 hover:bg-brand-500 disabled:opacity-50 px-4 py-2 text-white"
        onClick={send}
        disabled={loading || !input.trim()}
      >
        Send
      </button>
    </>
  );
}
