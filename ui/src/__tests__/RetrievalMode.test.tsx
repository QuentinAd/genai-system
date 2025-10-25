import { fireEvent, render, screen, within } from "@testing-library/react";
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

test("mode toggles are mutually exclusive and persist per session", async () => {
  const { unmount } = render(<App />);
  await act(async () => {
    await Promise.resolve();
  });
  const hiragToggle = screen.getByRole("button", { name: /enable hirag retrieval/i });
  const ragToggle = screen.getByRole("button", { name: /enable rag retrieval/i });

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
  await act(async () => {
    await Promise.resolve();
  });
  const persistedHirag = screen.getByRole("button", { name: /enable hirag retrieval/i });
  const persistedRag = screen.getByRole("button", { name: /enable rag retrieval/i });
  expect(persistedHirag).toHaveAttribute("aria-pressed", "false");
  expect(persistedRag).toHaveAttribute("aria-pressed", "true");
});

test("selected mode adds query param to chat request", async () => {
  render(<App />);
  await act(async () => {
    await Promise.resolve();
  });
  const hiragToggle = screen.getByRole("button", { name: /enable hirag retrieval/i });
  fireEvent.click(hiragToggle);

  fireEvent.change(screen.getByPlaceholderText("Type your message..."), {
    target: { value: "hello" },
  });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await Promise.resolve();
  });

  const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
  const hiragCall = fetchMock.mock.calls.find(([url]) => typeof url === "string" && url.includes("/chat?stream=events&hirag"));
  expect(hiragCall).toBeTruthy();

  fetchMock.mockClear();

  const ragToggle = screen.getByRole("button", { name: /enable rag retrieval/i });
  fireEvent.click(ragToggle);

  fireEvent.change(screen.getByPlaceholderText("Type your message..."), {
    target: { value: "second" },
  });

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await Promise.resolve();
  });

  const ragCall = fetchMock.mock.calls.find(([url]) => typeof url === "string" && url.includes("/chat?stream=events&rag"));
  expect(ragCall).toBeTruthy();
});

test("assistant messages show the mode badge", async () => {
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
  await act(async () => {
    await Promise.resolve();
  });
  const messageList = screen.getByTestId("message-list");

  expect(within(messageList).getByText("HiRAG mode")).toBeInTheDocument();
});
