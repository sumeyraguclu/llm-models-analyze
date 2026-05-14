import { cn } from "./utils";

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  className?: string;
}

export function Skeleton({ width = "100%", height = 16, className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg bg-surface2",
        "before:absolute before:inset-0 before:bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.08),transparent)]",
        "before:bg-[length:200%_100%] before:animate-shimmer",
        className,
      )}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

