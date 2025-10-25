import { fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import App from "../App";

const NOOP_RESPONSE = { body: null } as const;

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(NOOP_RESPONSE));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("mode toggles are mutually exclusive and persist per session", () => {
  const { unmount } = render(<App />);
  const hiragToggle = screen.getByRole("button", { name: /hirag retrieval/i });
  const ragToggle = screen.getByRole("button", { name: /rag retrieval/i });

  expect(hiragToggle).toHaveAttribute("aria-pressed", "false");
  expect(ragToggle).toHaveAttribute("aria-pressed", "false");

  fireEvent.click(hiragToggle);
  expect(hiragToggle).toHaveAttribute("aria-pressed", "true");
  expect(ragToggle).toHaveAttribute("aria-pressed", "false");
  expect(sessionStorage.getItem("chat_mode")).toBe("hirag");

  fireEvent.click(ragToggle);
  expect(hiragToggle).toHaveAttribute("aria-pressed", "false");
  expect(ragToggle).toHaveAttribute("aria-pressed", "true");
  expect(sessionStorage.getItem("chat_mode")).toBe("rag");

  unmount();

  render(<App />);
  const persistedHirag = screen.getByRole("button", { name: /hirag retrieval/i });
  const persistedRag = screen.getByRole("button", { name: /rag retrieval/i });
  expect(persistedHirag).toHaveAttribute("aria-pressed", "false");
  expect(persistedRag).toHaveAttribute("aria-pressed", "true");
});

test("selected mode adds query param to chat request", async () => {
  render(<App />);
  const hiragToggle = screen.getByRole("button", { name: /hirag retrieval/i });
  fireEvent.click(hiragToggle);

  fireEvent.change(screen.getByPlaceholderText("Type your message..."), {
    target: { value: "hello" },
  });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await Promise.resolve();
  });

  const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith("/chat?stream=events&hirag", expect.any(Object));

  fetchMock.mockClear();

  const ragToggle = screen.getByRole("button", { name: /rag retrieval/i });
  fireEvent.click(ragToggle);

  fireEvent.change(screen.getByPlaceholderText("Type your message..."), {
    target: { value: "second" },
  });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await Promise.resolve();
  });

  expect(fetchMock).toHaveBeenCalledWith("/chat?stream=events&rag", expect.any(Object));
});

test("assistant messages show the mode badge", () => {
  const timestamp = Date.now();
  localStorage.setItem(
    "chat_messages",
    JSON.stringify([
      {
        role: "assistant",
        content: "Hello user",
        timestamp,
        mode: "hirag",
      },
    ]),
  );

  render(<App />);

  expect(screen.getByText("HiRAG mode")).toBeInTheDocument();
});
