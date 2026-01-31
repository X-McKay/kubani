import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 [&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive transition-colors duration-150 overflow-hidden",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary/15 text-primary [a&]:hover:bg-primary/25",
        secondary:
          "border-border/50 bg-secondary/50 text-secondary-foreground [a&]:hover:bg-secondary/70",
        destructive:
          "border-transparent bg-destructive/15 text-destructive [a&]:hover:bg-destructive/25 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40",
        outline:
          "border-border/50 text-foreground [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        success:
          "border-transparent bg-success/15 text-success [a&]:hover:bg-success/25",
        warning:
          "border-transparent bg-warning/15 text-warning [a&]:hover:bg-warning/25",
        info:
          "border-transparent bg-info/15 text-info [a&]:hover:bg-info/25",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";

  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
