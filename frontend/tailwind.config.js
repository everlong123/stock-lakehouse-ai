/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--canvas))",
        surface: "hsl(var(--surface))",
        "surface-2": "hsl(var(--surface-2))",
        ink: "hsl(var(--ink))",
        muted: "hsl(var(--muted))",
        hairline: "hsl(var(--hairline))",
        primary: "hsl(var(--primary))",
        "on-primary": "hsl(var(--on-primary))",
        negative: "hsl(var(--negative))",
      },
      borderRadius: {
        // ONE working radius. Every rounded thing on the page is 6px;
        // `rounded-full` is the only exception (pills, dots, avatars).
        none: "0",
        sm: "6px",
        DEFAULT: "6px",
        md: "6px",
        lg: "6px",
        xl: "6px",
        "2xl": "6px",
        "3xl": "6px",
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
        // ONE elevation strategy: hairline borders, not shadows.
        // The only shadow allowed is for true overlays (popovers/dropdowns).
        none: "0 0 #0000",
        popover: "0 8px 24px -6px rgb(20 22 26 / 0.18)",
      },
    },
  },
  plugins: [],
};
