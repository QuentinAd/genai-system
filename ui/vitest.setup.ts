// Register Testing Library matchers with Vitest's expect
import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// Polyfill scrollIntoView for JSDOM
Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
  value: vi.fn(),
  writable: true,
})
