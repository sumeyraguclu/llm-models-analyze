import { type ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "./utils";
import { Spinner } from "./Spinner";

type ButtonVariant = "primary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-black hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed",
  ghost:
    "bg-transparent text-accent border border-border hover:bg-surface2 disabled:opacity-50 disabled:cursor-not-allowed",
  danger:
    "bg-danger text-black hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-base",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", loading = false, disabled, children, ...props },
  ref,
) {
  const isDisabled = disabled || loading;

  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg transition-all duration-200",
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
      disabled={isDisabled}
      {...props}
    >
      {loading && <Spinner size="sm" className="border-surface2 border-t-black" />}
      {children}
    </button>
  );
});

