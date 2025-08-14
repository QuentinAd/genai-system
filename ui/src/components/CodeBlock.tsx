import React from "react";

export default function CodeBlock({
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
