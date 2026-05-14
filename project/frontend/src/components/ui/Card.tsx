import { type HTMLAttributes } from "react";

import { cn } from "./utils";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hover?: boolean;
}

export function Card({ className, hover = false, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "animate-fadeIn rounded-xl border border-border bg-surface p-6",
        hover && "hover:border-accentDim transition-colors duration-200",
        className,
      )}
      {...props}
    />
  );
}

