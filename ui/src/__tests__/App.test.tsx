import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("App", () => {
  let App: typeof import("../App").default;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.resetModules();
    process.env.VITE_BACKEND_URL = "http://example.com";
    vi.stubGlobal("crypto", {
      randomUUID: () => "session-for-test",
      getRandomValues: (arr: Uint8Array) => arr,
    });
    fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/chat_history") && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(
          new Response(JSON.stringify({ sessions: [], next: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.includes("/chat_history/") && (!init || init.method === "GET")) {
        return Promise.resolve(
          new Response(JSON.stringify({ messages: [], next: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    App = (await import("../App")).default;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses backend URL and cancels on stop", async () => {
    const cancel = vi.fn();
    const read = vi.fn(() => new Promise<IteratorResult<Uint8Array>>(() => {}));
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/chat_history") && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(
          new Response(JSON.stringify({ sessions: [], next: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/chat?stream=events")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers(),
          body: {
            getReader: () => ({ read, cancel }),
          },
        } as unknown as Response);
      }
      return Promise.reject(new Error(`Unhandled fetch ${url}`));
    });

    render(<App />);
    const input = screen.getByPlaceholderText("Type your message...");
    await userEvent.type(input, "Hello");
    await userEvent.click(screen.getByText("Send"));
    await screen.findByText("Stop");
    expect(fetch).toHaveBeenCalledWith(
      "http://example.com/chat?stream=events",
      expect.objectContaining({ method: "POST" }),
    );
    await userEvent.click(screen.getByText("Stop"));
    expect(cancel).toHaveBeenCalled();
  });

  it("updates assistant message with token events from NDJSON stream", async () => {
    const encoder = new TextEncoder();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
        c.enqueue(encoder.encode('{"event":"on_chat_model_start","data":{"input":"Hello"}}\n'));
        c.enqueue(encoder.encode('{"event":"token","data":"Hi"}\n'));
      },
    });

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/chat_history") && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(
          new Response(JSON.stringify({ sessions: [], next: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/chat?stream=events")) {
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "application/x-ndjson" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch ${url}`));
    });

    render(<App />);
    const input = screen.getByPlaceholderText("Type your message...");
    await userEvent.type(input, "Hello{enter}");
    const messageList = await screen.findByTestId("message-list");
    await within(messageList).findByText("Hi");
    await act(async () => {
      controller.enqueue(encoder.encode('{"event":"token","data":" there"}\n'));
      controller.enqueue(encoder.encode('{"event":"on_chat_model_end","data":{"output":"Hithere"}}\n'));
      controller.close();
    });
    await within(messageList).findByText("Hi there");
    const summary = await screen.findByText("Events (2)");
    await userEvent.click(summary);
    await screen.findByText("on_chat_model_start");
    await screen.findByText(/"input"\s*:\s*"Hello"/);
    await screen.findByText("on_chat_model_end");
  });

  it("stop button aborts the request", async () => {
    const abortSpy = vi.fn();
    const MockAbortController = class {
      signal = {};
      abort = abortSpy;
    };
    vi.stubGlobal("AbortController", MockAbortController as unknown as typeof AbortController);

    const stream = new ReadableStream<Uint8Array>({
      start() {
        /* keep open */
      },
    });

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/chat_history") && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(
          new Response(JSON.stringify({ sessions: [], next: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/chat?stream=events")) {
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "application/x-ndjson" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch ${url}`));
    });

    render(<App />);
    const input = screen.getByPlaceholderText("Type your message...");
    await userEvent.type(input, "Hello{enter}");
    const stopBtn = await screen.findByText("Stop");
    await userEvent.click(stopBtn);
    expect(abortSpy).toHaveBeenCalled();
  });

  it("theme toggler switches classes and localStorage", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/chat_history") && (!init || !init.method || init.method === "GET")) {
        return Promise.resolve(
          new Response(JSON.stringify({ sessions: [], next: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/chat?stream=events")) {
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.close();
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "application/x-ndjson" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled fetch ${url}`));
    });

    render(<App />);
    const button = screen.getByRole("button", { name: /mode/i });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");

    await userEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");

    await userEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
  });
});
