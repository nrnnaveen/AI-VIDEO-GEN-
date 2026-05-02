/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['var(--font-display)', 'serif'],
        mono:    ['var(--font-mono)',    'monospace'],
      },
      colors: {
        void:   '#05050a',
        ember:  '#ff5c1a',
        plasma: '#c445f0',
        ice:    '#3ae8ff',
      },
      keyframes: {
        pulse_ring: {
          '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
          '50%':       { opacity: '0.9', transform: 'scale(1.08)' },
        },
        scanline: {
          '0%':   { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '0 100px' },
        },
        reveal: {
          '0%':   { opacity: '0', transform: 'translateY(18px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        pulse_ring: 'pulse_ring 2s ease-in-out infinite',
        scanline:   'scanline 3s linear infinite',
        reveal:     'reveal 0.6s ease forwards',
      },
    },
  },
  plugins: [],
};
