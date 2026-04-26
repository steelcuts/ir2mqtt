/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ha: { 
          500: 'rgb(var(--color-accent) / <alpha-value>)',
        },
        gray: {
          900: 'rgb(var(--color-bg-primary) / <alpha-value>)',
          800: 'rgb(var(--color-bg-secondary) / <alpha-value>)',
          700: 'rgb(var(--color-bg-tertiary) / <alpha-value>)',
          600: 'rgb(var(--color-border) / <alpha-value>)',
          500: 'rgb(var(--color-text-secondary) / <alpha-value>)',
          400: 'rgb(var(--color-text-secondary) / <alpha-value>)',
          300: 'rgb(var(--color-text-primary) / <alpha-value>)',
          200: 'rgb(var(--color-text-primary) / <alpha-value>)',
        },
        green: {
          400: 'rgb(var(--color-success) / <alpha-value>)',
          500: 'rgb(var(--color-success) / <alpha-value>)',
          900: 'rgb(var(--color-success) / <alpha-value>)',
        },
        yellow: {
          300: 'rgb(var(--color-warning) / <alpha-value>)',
          400: 'rgb(var(--color-warning) / <alpha-value>)',
        },
        blue: {
          400: 'rgb(var(--color-accent) / <alpha-value>)',
          500: 'rgb(var(--color-accent) / <alpha-value>)',
          600: 'rgb(var(--color-accent) / <alpha-value>)',
          700: 'rgb(var(--color-accent-hover) / <alpha-value>)',
          900: 'rgb(var(--color-accent) / <alpha-value>)',
        },
        red: {
          400: 'rgb(var(--color-danger) / <alpha-value>)',
          500: 'rgb(var(--color-danger) / <alpha-value>)',
          900: 'rgb(var(--color-danger) / <alpha-value>)',
        },
        purple: {
          400: 'rgb(var(--color-purple) / <alpha-value>)',
          500: 'rgb(var(--color-purple) / <alpha-value>)',
          900: 'rgb(var(--color-purple) / <alpha-value>)',
        },
        pink: {
          400: 'rgb(var(--color-pink) / <alpha-value>)',
          500: 'rgb(var(--color-pink) / <alpha-value>)',
          900: 'rgb(var(--color-pink) / <alpha-value>)',
        },
        orange: {
          400: 'rgb(var(--color-orange) / <alpha-value>)',
          500: 'rgb(var(--color-orange) / <alpha-value>)',
          900: 'rgb(var(--color-orange) / <alpha-value>)',
        },
        cyan: {
          400: 'rgb(var(--color-cyan) / <alpha-value>)',
          500: 'rgb(var(--color-cyan) / <alpha-value>)',
          900: 'rgb(var(--color-cyan) / <alpha-value>)',
        },
        indigo: {
          400: 'rgb(var(--color-indigo) / <alpha-value>)',
          500: 'rgb(var(--color-indigo) / <alpha-value>)',
        }
      }
    },
  },
  plugins: [],
}
