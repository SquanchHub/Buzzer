import type { Config } from 'tailwindcss';

// T9 "Riso Press" theme (docs/plans/t9-theming.md §3, D1). `colors` REPLACES Tailwind's
// palette: only semantic tokens exist, so a raw `bg-slate-800` generates nothing.
// The values are CSS variables from the token block in src/index.css.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const names = [
  'canvas', 'surface', 'sunken', 'ink', 'ink-muted', 'ink-soft', 'line', 'line-soft', 'shadow',
  'accent', 'accent-ink', 'success', 'success-ink', 'danger', 'danger-ink', 'warning',
  'warning-ink', 'focus', 'on-fill', 'qr', 'scrim',
  'opt-1', 'opt-2', 'opt-3', 'opt-4', 'opt-5', 'opt-6', 'opt-7', 'opt-8',
] as const;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',
      ...Object.fromEntries(names.map((n) => [n, token(n)])),
    },
    extend: {
      fontFamily: {
        sans: ['"Bricolage Grotesque Variable"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        display: ['"Bricolage Grotesque Variable"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        'hard-sm': '2px 2px 0 0 rgb(var(--shadow))',
        hard: '4px 4px 0 0 rgb(var(--shadow))',
        'hard-lg': '6px 6px 0 0 rgb(var(--shadow))',
      },
      ringColor: {
        DEFAULT: 'rgb(var(--focus))',
      },
    },
  },
  plugins: [],
} satisfies Config;
