/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // The dark theme is a re-palette of the SAME roles, applied by a
  // `data-theme` attribute on <html>. It is NOT Tailwind's `darkMode:
  // "class"` strategy, because every colour in this app resolves through
  // a CSS custom property (`hsl(var(--ink))` and friends). Redefining the
  // property under `[data-theme="dark"]` repaints everything - including
  // the recharts charts, which read the same variables - in a single
  // style recalculation, with no component needing to know a theme
  // exists.
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--canvas))",
        surface: "hsl(var(--surface))",
        "surface-2": "hsl(var(--surface-2))",
        "surface-3": "hsl(var(--surface-3))",
        ink: "hsl(var(--ink))",
        muted: "hsl(var(--muted))",
        hairline: "hsl(var(--hairline))",
        primary: "hsl(var(--primary))",
        "primary-2": "hsl(var(--primary-2))",
        "on-primary": "hsl(var(--on-primary))",
        negative: "hsl(var(--negative))",
        up: "hsl(var(--up))",
      },
      borderRadius: {
        // ONE working radius. Every rounded thing on the page is 8px;
        // `rounded-full` is the only exception (pills, dots, avatars).
        none: "0",
        sm: "8px",
        DEFAULT: "8px",
        md: "8px",
        lg: "8px",
        xl: "8px",
        "2xl": "8px",
        "3xl": "8px",
        full: "9999px",
      },
      fontFamily: {
        // Headings, body, numbers — three different voices on purpose.
        display: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        sans: ["DM Sans", "system-ui", "-apple-system", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // FIVE sizes. Nothing else is allowed.
        display: ["40px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "600" }],
        heading: ["24px", { lineHeight: "1.3", letterSpacing: "-0.01em", fontWeight: "600" }],
        body: ["16px", { lineHeight: "1.6" }],
        small: ["14px", { lineHeight: "1.5" }],
        label: ["12px", { lineHeight: "1.4", letterSpacing: "0.04em", fontWeight: "500" }],
      },
      boxShadow: {
        // A deliberate elevation SCALE rather than one flat strategy.
        // The chart panels, the popovers and the raised rows need to
        // separate from the canvas, and a screen where every region is
        // the same flat rectangle is hard to read.
        none: "0 0 #0000",
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        popover: "var(--shadow-popover)",
      },
      // The theme crossfade needs no keyframes of its own - they live in
      // index.css - but the durations are declared here so a component
      // can use `duration-theme` without inventing a number.
      transitionDuration: {
        theme: "320ms",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translate3d(0, 8px, 0)" },
          to: { opacity: "1", transform: "translate3d(0, 0, 0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-up": "fade-up 320ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 220ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "scale-in": "scale-in 180ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
};
