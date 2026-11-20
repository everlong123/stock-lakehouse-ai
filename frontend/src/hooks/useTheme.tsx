import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * The theme: light, dark, or "follow the operating system".
 *
 * WHY THIS IS A CONTEXT AND NOT A CLASS ON <html>
 * ----------------------------------------------
 * The palette is defined as CSS custom properties and re-defined under
 * `[data-theme="dark"]`. So the ONLY thing the app has to do to switch
 * themes is set one attribute on the root element. No component is
 * re-rendered with a different prop, no chart is told to repaint with
 * new colours, and no CSS is duplicated.
 *
 * WHY THE CHOICE IS STORED
 * ------------------------
 * A reader who picks the dark theme expects it to still be dark when
 * they come back tomorrow. So the explicit choice is written to
 * `localStorage` and read back on the next load. "system" is the default
 * because most people never open the switch, and they should get
 * whatever their OS is doing without asking.
 *
 * WHY THE INITIAL SCRIPT IS IN index.html AND NOT HERE
 * ----------------------------------------------------
 * The theme has to be applied BEFORE the first paint. If React decided
 * it, the page would flash light and then jump to dark - the classic
 * "flash of wrong theme" that every dark-mode site has to solve. A
 * tiny inline script in the document head reads the stored value and
 * sets the attribute synchronously, before the browser paints anything.
 * See `index.html`.
 *
 * WHY `system` IS WATCHED
 * -----------------------
 * The OS theme can change while the app is open (macOS auto light/dark,
 * Windows "light" setting). If the reader chose "system", the app
 * follows it live; if they chose an explicit theme, it does not.
 */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

interface ThemeContextValue {
  /** What the reader chose. */
  preference: ThemePreference;
  /** What is actually on screen right now. */
  theme: ResolvedTheme;
  setPreference: (next: ThemePreference) => void;
  /** Flip between light and dark, starting from whatever is on screen. */
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "stock-lakehouse-theme";

/** The OS preference, resolved to a theme name. */
function systemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readStoredPreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" || stored === "system"
    ? stored
    : "system";
}

/**
 * Apply the theme to the document root.
 *
 * WHY THE ATTRIBUTE AND NOT A CLASS: `darkMode: ["class", '[data-theme="dark"]']`
 * in the Tailwind config lets BOTH spellings work, but the attribute is
 * used here because the CSS custom properties are keyed off it, and the
 * custom properties are what the charts read.
 */
function applyTheme(theme: ResolvedTheme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  // Keep the browser chrome (the mobile address bar, the OS window
  // title bar) in the same palette as the page. Without this the mobile
  // Safari toolbar stays white above a dark page.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", theme === "dark" ? "#0B0E16" : "#F1F3F8");
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference);
  const [theme, setTheme] = useState<ResolvedTheme>(() =>
    preference === "system" ? systemTheme() : preference,
  );

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
    }
    const resolved = next === "system" ? systemTheme() : next;
    setTheme(resolved);
    applyTheme(resolved);
  }, []);

  // Follow the OS while the preference is "system".
  useEffect(() => {
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const resolved = systemTheme();
      setTheme(resolved);
      applyTheme(resolved);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  // Keep the root attribute in sync if the theme changed another way
  // (the OS event above, or the initial mount).
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setPreference(theme === "dark" ? "light" : "dark");
  }, [theme, setPreference]);

  const value = useMemo(
    () => ({ preference, theme, setPreference, toggle }),
    [preference, theme, setPreference, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    return {
      preference: "system",
      theme: "light",
      setPreference: () => undefined,
      toggle: () => undefined,
    };
  }
  return ctx;
}
