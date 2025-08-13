import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

// Consolidated Tailwind config (migrated from tailwind.config.cjs)
const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f7ff',
          100: '#e0efff',
          200: '#b9dbff',
          300: '#89c2ff',
          400: '#57a6ff',
          500: '#2b8aff',
          600: '#0a6ff6',
          700: '#0559c7',
          800: '#064aa0',
          900: '#0a3f82',
        },
      },
    },
  },
  plugins: [typography],
}

export default config
