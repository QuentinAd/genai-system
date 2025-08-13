import type { Config } from 'tailwindcss'

// Minimal TS stub; actual config is in tailwind.config.cjs
const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: { extend: {} },
  plugins: [],
}

export default config
