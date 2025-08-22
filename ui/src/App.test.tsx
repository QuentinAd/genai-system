import { fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { vi } from 'vitest'
import App from './App'

test('debounces writes to localStorage when messages update', async () => {
  vi.useFakeTimers()
  const setItem = vi.spyOn(Storage.prototype, 'setItem')
  render(<App />)
  setItem.mockClear()

  fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
    target: { value: 'hello' },
  })
  fireEvent.click(screen.getByText('Send'))

  expect(setItem).not.toHaveBeenCalledWith('chat_messages', expect.anything())

  await act(async () => {
    await vi.advanceTimersByTimeAsync(500)
  })

  expect(setItem).toHaveBeenCalledWith(
    'chat_messages',
    expect.stringContaining('hello'),
  )
  vi.useRealTimers()
})
