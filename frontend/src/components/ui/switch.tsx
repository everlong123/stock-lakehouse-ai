import { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface SwitchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
}

export function Switch({ checked, onCheckedChange, className, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative h-5 w-9 rounded-full transition-colors",
        checked ? "bg-primary" : "bg-muted",
        className,
      )}
      {...props}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
          checked ? "left-4" : "left-0.5",
        )}
      />
    </button>
  );
}
