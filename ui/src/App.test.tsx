import { fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("App local persistence", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("crypto", {
      randomUUID: () => "session-under-test",
      getRandomValues: (arr: Uint8Array) => arr,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith("/chat_history") && (!init || !init.method || init.method === "GET")) {
          return Promise.resolve(
            new Response(JSON.stringify({ sessions: [], next: null }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        if (url.endsWith("/chat") && init?.method === "POST") {
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
      }),
    );
  });

  it("debounces writes to localStorage when messages update", async () => {
    vi.useFakeTimers();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { default: App } = await import("./App");
    render(<App />);
    setItem.mockClear();

    fireEvent.change(screen.getByPlaceholderText("Type your message..."), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByText("Send"));

    expect(setItem).not.toHaveBeenCalledWith("chat_messages", expect.anything());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(setItem).toHaveBeenCalledWith(
      "chat_messages",
      expect.stringContaining("hello"),
    );
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});
