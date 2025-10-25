import { render, screen, act, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

process.env.VITE_BACKEND_URL = "";

const sampleSessions = [
  {
    session_id: "session-1",
    updated_at: "2024-01-01T12:00:00Z",
    preview: "First conversation",
    mode: "hi",
  },
  {
    session_id: "session-2",
    updated_at: 1700000000,
    preview: "Second conversation",
    mode: "llm",
  },
];

const baseHistory = {
  messages: [
    { role: "user", content: "Hi", timestamp: 1000, mode: "llm" },
    { role: "assistant", content: "Hello there", timestamp: 2000, mode: "llm" },
  ],
  next: "older",
};

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("Chat history panel", () => {
  let App: typeof import("../App").default;
  let confirmSpy: ReturnType<typeof vi.spyOn>;
  const fetchSpy = vi.fn();

  beforeEach(async () => {
    vi.resetModules();
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("crypto", {
      randomUUID: () => "local-session",
      // vitest may call getRandomValues when creating uuid in other libs
      getRandomValues: (arr: Uint8Array) => arr,
    });
    fetchSpy.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/chat_history") && (!init || init.method === undefined || init.method === "GET")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ sessions: sampleSessions, next: null }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.endsWith("/chat_history/session-1")) {
        return Promise.resolve(
          new Response(JSON.stringify(baseHistory), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/chat_history/session-1?cursor=older")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              messages: [
                { role: "user", content: "Older", timestamp: 10, mode: "llm" },
              ],
              next: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.endsWith("/chat_history/session-1") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith("/chat") && init?.method === "POST") {
        return Promise.resolve(
          new Response(null, {
            status: 200,
            headers: { "Content-Type": "application/x-ndjson" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch ${url}`));
    });
    vi.stubGlobal("fetch", fetchSpy as unknown as typeof fetch);
    App = (await import("../App")).default;
  });

  afterEach(() => {
    fetchSpy.mockReset();
    confirmSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("renders conversations and toggles the panel", async () => {
    render(<App />);
    expect(await screen.findByText("First conversation")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /toggle conversations panel/i });
    await userEvent.click(toggle);
    expect(screen.queryByRole("complementary", { name: /conversations/i })).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.getByRole("complementary", { name: /conversations/i })).toBeInTheDocument();
  });

  it("loads history when a conversation is selected", async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /first conversation/i }));
    const messageList = await screen.findByTestId("message-list");
    expect(await within(messageList).findByText("Hello there")).toBeInTheDocument();
    expect(
      fetchSpy.mock.calls.some(
        ([url, init]) =>
          typeof url === "string" &&
          url.includes("/chat_history/session-1") &&
          (!init || (init as RequestInit).method === "GET"),
      ),
    ).toBe(true);
  });

  it("supports lazy loading older history when scrolling to top", async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /first conversation/i }));
    const historyContainer = await screen.findByTestId("message-list");
    await within(historyContainer).findByText("Hello there");
    await act(async () => {
      historyContainer.scrollTop = 0;
      fireEvent.scroll(historyContainer);
    });

    await flushPromises();
    expect(
      fetchSpy.mock.calls.some(
        ([url, init]) =>
          typeof url === "string" &&
          url.includes("/chat_history/session-1?cursor=older") &&
          (!init || (init as RequestInit).method === "GET"),
      ),
    ).toBe(true);
    expect(await within(historyContainer).findByText("Older")).toBeInTheDocument();
  });

  it("clears history after confirmation", async () => {
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /first conversation/i }));
    const messageList = await screen.findByTestId("message-list");
    await within(messageList).findByText("Hello there");

    const clearButton = screen.getByRole("button", { name: /clear history/i });
    await userEvent.click(clearButton);

    expect(
      fetchSpy.mock.calls.some(
        ([url, init]) =>
          typeof url === "string" &&
          url.includes("/chat_history/session-1") &&
          (init as RequestInit | undefined)?.method === "DELETE",
      ),
    ).toBe(true);
    await flushPromises();
    expect(within(messageList).queryByText("Hello there")).not.toBeInTheDocument();
  });
});
