/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  // We toggle the .dark class on <html> ourselves (see useAppStore.setTheme).
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Bound to CSS variables so the same class names work for both themes.
        // Values live in src/index.css under :root (light) and .dark.
        bg: {
          DEFAULT: 'var(--color-bg)',
          sidebar: 'var(--color-bg-sidebar)',
          panel: 'var(--color-bg-panel)',
          hover: 'var(--color-bg-hover)',
          active: 'var(--color-bg-active)',
          titlebar: 'var(--color-bg-titlebar)',
        },
        border: {
          DEFAULT: 'var(--color-border)',
          strong: 'var(--color-border-strong)',
          subtle: 'var(--color-border-subtle)',
        },
        fg: {
          DEFAULT: 'var(--color-fg)',
          muted: 'var(--color-fg-muted)',
          subtle: 'var(--color-fg-subtle)',
          faint: 'var(--color-fg-faint)',
        },
        accent: {
          DEFAULT: 'var(--color-accent)',
          hover: 'var(--color-accent-hover)',
          subtle: 'var(--color-accent-subtle)',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      fontSize: {
        '2xs': ['11px', { lineHeight: '14px' }],
        xs: ['12px', { lineHeight: '16px' }],
        sm: ['13px', { lineHeight: '18px' }],
        base: ['14px', { lineHeight: '20px' }],
      },
      borderRadius: {
        pill: '14px',
      },
      boxShadow: {
        popup:
          '0 12px 28px -4px rgba(0,0,0,0.55), 0 4px 8px -2px rgba(0,0,0,0.35)',
      },
      keyframes: {
        pulseDot: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
