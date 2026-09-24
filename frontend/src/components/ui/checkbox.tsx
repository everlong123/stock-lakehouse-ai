import { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
}

export function Checkbox({ label, className, ...props }: CheckboxProps) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        className={cn("h-4 w-4 accent-primary", className)}
        {...props}
      />
      {label}
    </label>
  );
}
