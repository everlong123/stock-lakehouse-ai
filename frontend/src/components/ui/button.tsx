import { cva, type VariantProps } from "class-variance-authority";
import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

/**
 * Buttons.
 *
 * WHY FOUR VARIANTS AND NOT SIX: the four cover every real case, and the
 * rule that matters is "one filled accent per view". `primary` is the
 * action; `secondary` is the alternative; `outline` is a quiet action in
 * a group; `text` is a tertiary link-ish action. A second `primary` on the
 * same screen dilutes the first one.
 *
 * No gradients, no shadows, one radius (6px).
 */
const buttonVariants = cva(
  "btn focus-visible:outline-none",
  {
    variants: {
      variant: {
        primary: "btn-primary",
        secondary: "btn-secondary",
        outline: "btn-outline",
        text: "btn-text",
      },
      size: {
        default: "btn-h",
        sm: "btn-sm",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variant: "outline", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";
