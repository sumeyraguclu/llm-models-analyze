import { cn } from "./utils";

export interface DividerProps {
  className?: string;
}

export function Divider({ className }: DividerProps) {
  return <hr className={cn("border-0 border-t border-border", className)} />;
}

