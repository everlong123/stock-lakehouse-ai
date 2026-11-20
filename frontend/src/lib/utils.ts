import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * WHY THIS FILE HAS A TAILWIND-MERGE CONFIGURATION
 * ---------------------------------------------
 * `tailwind-merge` decides which of two conflicting classes wins. It
 * knows the classes from Tailwind's own default scale, and this project
 * extends that scale with its own type ramp:
 *
 *   text-display  text-heading  text-body  text-small  text-label
 *
 * Those five names look exactly like Tailwind's colour utilities
 * (`text-red-500`, `text-blue-600`, ...), so an un-configured
 * tailwind-merge files every `text-*` under the *text colour* group.
 * The consequence is silent and severe: given
 *
 *   cn("text-display text-up")
 *
 * the merge sees two colour classes, keeps the last one, and throws the
 * 40px display size away. The element ends up 14px and nobody knows
 * why - the class list still contains "text-display".
 *
 * So the custom type ramp is declared here as a *font size* group, and
 * `text-up` / `text-negative` / `text-ink` / `text-muted` stay in the
 * colour group. The two roles can then coexist, which is exactly what
 * the quote header needs: a 40px price that is also coloured by the
 * direction of the move.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: ["display", "heading", "body", "small", "label"],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
