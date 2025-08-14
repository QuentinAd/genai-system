import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import MessageInput from "../components/MessageInput";

describe("MessageInput", () => {
  it("calls send on Enter", async () => {
    const send = vi.fn();
    const setInput = vi.fn();
    render(
      <MessageInput
        input="Hello"
        setInput={setInput}
        send={send}
        loading={false}
      />,
    );
    const textarea = screen.getByPlaceholderText("Type your message...");
    await userEvent.type(textarea, "{enter}");
    expect(send).toHaveBeenCalled();
  });
});
