import { render, screen } from "@testing-library/react";
import MessageList from "../components/MessageList";

describe("MessageList", () => {
  it("renders messages", () => {
    const messages = [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
    ];
    const endRef = { current: null };
    render(<MessageList messages={messages} endRef={endRef} />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });
});
