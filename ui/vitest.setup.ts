// Register Testing Library matchers with Vitest's expect
import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Polyfill scrollIntoView for JSDOM
Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
  value: vi.fn(),
  writable: true,
});

class MockIntersectionObserver {
  readonly observe = vi.fn();
  readonly disconnect = vi.fn();
  readonly unobserve = vi.fn();
  constructor() {
    /* no-op */
  }
}

(globalThis as typeof globalThis & { IntersectionObserver?: typeof IntersectionObserver }).IntersectionObserver =
  MockIntersectionObserver as unknown as typeof IntersectionObserver;
