/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        border: "hsl(var(--border))",
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        up: "hsl(var(--up))",
        down: "hsl(var(--down))",
      },
      borderRadius: {
        lg: "12px",
        md: "10px",
        sm: "8px",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
