import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

/**
 * The theme switch.
 *
 * WHY IT IS THREE STATES AND NOT TWO
 * ----------------------------------
 * "Light / dark" is not enough on its own: a reader whose operating
 * system is in dark mode usually wants the app dark too, and having to
 * re-pick "dark" after every OS change is a chore. So the switch offers
 * the third real option — follow the system — and remembers it.
 *
 * WHY A SEGMENTED CONTROL AND NOT ONE TOGGLE BUTTON
 * -------------------------------------------------
 * A single toggle button is faster to reach for, but it cannot express
 * "follow the system". Three small icons in a row say all three states
 * at once, and the ACTIVE one is the one that is filled, so the current
 * state is legible without reading any text.
 *
 * WHY THE ICONS ARE FROM LUCIDE
 * -----------------------------
 * `Sun`, `Moon` and `Monitor` are the three states the whole industry
 * uses for this, and they are unambiguous at 14px.
 *
 * WHY THE BUTTONS ARE TALLER THAN THE ICON
 * ---------------------------------------
 * A 28px target is below the 44px touch-target floor the design system
 * sets for mobile. The control keeps a 36px row so it can be hit with a
 * thumb; the icons inside stay small.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { preference, setPreference } = useTheme();

  const options: Array<{
    value: ThemePreference;
    icon: typeof Sun;
    label: string;
  }> = [
    { value: "light", icon: Sun, label: "Giao diện sáng" },
    { value: "dark", icon: Moon, label: "Giao diện tối" },
    { value: "system", icon: Monitor, label: "Theo hệ thống" },
  ];

  return (
    <div
      className={cn(
        "inline-flex items-center gap-0.5 rounded border border-hairline bg-surface-2 p-0.5",
        className,
      )}
      role="radiogroup"
      aria-label="Giao diện"
    >
      {options.map((option) => {
        const active = preference === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setPreference(option.value)}
            title={option.label}
            aria-label={option.label}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded transition-colors",
              active
                ? "bg-primary text-on-primary"
                : "text-muted hover:bg-surface-3 hover:text-ink",
            )}
          >
            <option.icon size={14} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
