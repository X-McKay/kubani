# Phase 0: Visual Design System

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** None
**Estimated scope:** ~15 files modified

---

## Overview

Establish the visual foundation for the entire UI redesign. Every subsequent phase builds on these design tokens, surface treatments, animation utilities, and component overrides. This phase changes NO functionality — only visual presentation.

---

## Goals

1. Replace heavy glassmorphism with refined matte dark surfaces
2. Establish consistent spacing and typography scale
3. Add micro-animation utilities for transitions and hover states
4. Update all shadcn/ui component overrides for new aesthetic
5. Reduce background orb intensity
6. Ensure WCAG AA contrast compliance

---

## 1. Color Token Changes

### File: `client/src/index.css`

Replace the `:root` block with updated values. Changes are annotated with `/* CHANGED */` or `/* NEW */`.

```css
:root {
  --radius: 0.625rem;  /* CHANGED: 10px (was 12px) — slightly tighter corners */

  /* Base colors — deeper, less purple tint */
  --background: oklch(0.09 0.015 285);      /* CHANGED: darker base (was 0.11 0.02) */
  --foreground: oklch(0.95 0.005 285);       /* CHANGED: slightly softer white (was 0.98) */

  /* Card/Surface — solid, not transparent */
  --card: oklch(0.12 0.012 285);             /* CHANGED: darker, less chroma (was 0.16 0.015) */
  --card-foreground: oklch(0.95 0.005 285);  /* CHANGED: match foreground */

  /* NEW: Elevated surface for overlays, modals, popovers */
  --card-elevated: oklch(0.14 0.015 285);    /* NEW */

  /* Popover — use elevated surface */
  --popover: oklch(0.14 0.015 285);          /* CHANGED: match card-elevated (was 0.14 0.02) */
  --popover-foreground: oklch(0.95 0.005 285);

  /* Primary — Vibrant violet (unchanged) */
  --primary: oklch(0.65 0.25 285);
  --primary-foreground: oklch(0.98 0.005 285);

  /* Secondary — Slightly lighter for better visibility */
  --secondary: oklch(0.18 0.02 285);         /* CHANGED: was 0.22 0.03 */
  --secondary-foreground: oklch(0.85 0.02 285);

  /* Muted — Better differentiation from card */
  --muted: oklch(0.15 0.015 285);            /* CHANGED: was 0.20 0.02 */
  --muted-foreground: oklch(0.55 0.015 285); /* CHANGED: slightly dimmer for hierarchy */

  /* Accent — Cyan (unchanged) */
  --accent: oklch(0.75 0.15 195);
  --accent-foreground: oklch(0.15 0.02 285);

  /* Destructive — Rose (unchanged) */
  --destructive: oklch(0.65 0.2 15);
  --destructive-foreground: oklch(0.98 0.005 285);

  /* Border — More visible for matte aesthetic */
  --border: oklch(0.22 0.015 285);           /* CHANGED: more visible (was 0.30 0.02) */
  --border-subtle: oklch(0.17 0.01 285);     /* NEW: for separators, dividers */
  --input: oklch(0.18 0.015 285);            /* CHANGED: match border area (was 0.25) */
  --ring: oklch(0.65 0.25 285);

  /* Chart colors (unchanged) */
  --chart-1: oklch(0.65 0.25 285);
  --chart-2: oklch(0.75 0.15 195);
  --chart-3: oklch(0.70 0.18 155);
  --chart-4: oklch(0.75 0.15 85);
  --chart-5: oklch(0.65 0.2 15);

  /* Sidebar — Slightly darker than card */
  --sidebar: oklch(0.10 0.015 285);          /* CHANGED: darker (was 0.13 0.02) */
  --sidebar-foreground: oklch(0.80 0.015 285); /* CHANGED: slightly dimmer */
  --sidebar-primary: oklch(0.65 0.25 285);
  --sidebar-primary-foreground: oklch(0.98 0.005 285);
  --sidebar-accent: oklch(0.16 0.02 285);    /* CHANGED: (was 0.20 0.03) */
  --sidebar-accent-foreground: oklch(0.95 0.005 285);
  --sidebar-border: oklch(0.20 0.015 285);   /* CHANGED: (was 0.25 0.02) */
  --sidebar-ring: oklch(0.65 0.25 285);

  /* Status colors (unchanged) */
  --success: oklch(0.70 0.18 155);
  --warning: oklch(0.75 0.15 85);
  --error: oklch(0.65 0.2 15);

  /* NEW: Status semantic colors */
  --info: oklch(0.65 0.15 240);              /* NEW: blue for informational */
}
```

### New Theme Variables to Register

Add to the `@theme inline` block:

```css
@theme inline {
  /* ... existing mappings ... */

  /* NEW mappings */
  --color-card-elevated: var(--card-elevated);
  --color-border-subtle: var(--border-subtle);
  --color-info: var(--info);
  --color-success: var(--success);
  --color-warning: var(--warning);
  --color-error: var(--error);
}
```

---

## 2. Surface Treatment System

### Replace Glass Classes

**Remove:**
```css
/* DELETE these classes */
.glass {
  @apply bg-card/60 backdrop-blur-xl border border-white/10 shadow-xl;
}

.glass-subtle {
  @apply bg-card/40 backdrop-blur-md border border-white/5;
}
```

**Add:**
```css
@layer components {
  /* Primary surface — solid matte panel */
  .surface {
    @apply bg-card border border-border/50 rounded-xl;
  }

  /* Elevated surface — for panels that float above (modals, sheets, popovers) */
  .surface-elevated {
    @apply bg-card-elevated border border-border/60 rounded-xl shadow-lg;
  }

  /* Interactive surface — for clickable cards, list items */
  .surface-interactive {
    @apply bg-card border border-border/40 rounded-xl
           hover:bg-card-elevated hover:border-border/70
           transition-all duration-200 ease-out;
  }

  /* Inset surface — for input fields, code blocks, nested content */
  .surface-inset {
    @apply bg-background border border-border/30 rounded-lg;
  }

  /* Glass — RESERVED for overlays, mobile nav, command palette only */
  .glass {
    @apply bg-card/80 backdrop-blur-md border border-border/40 rounded-xl shadow-xl;
  }
}
```

### Where Each Surface Is Used

| Surface Class | Use Cases |
|---------------|-----------|
| `.surface` | Sidebar, page sections, static cards, panels |
| `.surface-elevated` | Side panels, dropdowns, popovers, toasts |
| `.surface-interactive` | Feed items, registry cards, workflow rows, clickable cards |
| `.surface-inset` | Input fields, code blocks, nested content areas |
| `.glass` | Command palette overlay, mobile navigation sheet, modals |

---

## 3. Typography System

### Add Typography Utilities

```css
@layer utilities {
  /* Headings */
  .text-heading-1 {
    @apply text-2xl font-semibold tracking-tight leading-tight;
    /* 24px, semibold */
  }

  .text-heading-2 {
    @apply text-xl font-semibold tracking-tight leading-tight;
    /* 20px, semibold */
  }

  .text-heading-3 {
    @apply text-lg font-medium leading-snug;
    /* 18px, medium */
  }

  /* Body */
  .text-body {
    @apply text-sm leading-relaxed;
    /* 14px — Factory.ai's base text size */
  }

  .text-body-lg {
    @apply text-base leading-relaxed;
    /* 16px */
  }

  /* Labels and captions */
  .text-label {
    @apply text-xs font-medium uppercase tracking-wider text-muted-foreground;
    /* 12px, uppercase, muted */
  }

  .text-caption {
    @apply text-xs text-muted-foreground leading-normal;
    /* 12px, muted */
  }

  /* Mono (code, IDs, technical) */
  .text-mono {
    @apply font-mono text-xs;
  }
}
```

---

## 4. Spacing System

### Layout Spacing Utilities

```css
@layer utilities {
  /* Page-level spacing */
  .page-padding {
    @apply px-6 py-6 lg:px-8 lg:py-8;
  }

  /* Section spacing within a page */
  .section-gap {
    @apply space-y-6 lg:space-y-8;
  }

  /* Card internal padding */
  .card-padding {
    @apply p-4 lg:p-5;
  }

  /* Compact card padding (list items, feed items) */
  .card-padding-compact {
    @apply p-3 lg:p-4;
  }

  /* Grid gaps */
  .grid-gap {
    @apply gap-4 lg:gap-5;
  }

  /* Stack spacing variants */
  .stack-xs { @apply space-y-1; }
  .stack-sm { @apply space-y-2; }
  .stack-md { @apply space-y-3; }
  .stack-lg { @apply space-y-4; }
  .stack-xl { @apply space-y-6; }
}
```

### Container Updates

Replace existing `.container` in `@layer components`:

```css
@layer components {
  .container {
    width: 100%;
    margin-left: auto;
    margin-right: auto;
    padding-left: 1rem;       /* 16px mobile */
    padding-right: 1rem;
  }

  @media (min-width: 640px) {
    .container {
      padding-left: 1.5rem;   /* 24px tablet */
      padding-right: 1.5rem;
    }
  }

  @media (min-width: 1024px) {
    .container {
      padding-left: 2.25rem;  /* 36px — CHANGED from 2rem */
      padding-right: 2.25rem;
      max-width: 1400px;
    }
  }

  @media (min-width: 1536px) {
    .container {
      padding-left: 3rem;     /* 48px — more generous on wide screens */
      padding-right: 3rem;
    }
  }
}
```

---

## 5. Animation & Transition System

### Base Transitions

```css
@layer utilities {
  /* Standard interactive transition */
  .transition-interactive {
    @apply transition-all duration-200 ease-out;
  }

  /* Smooth transition for layout changes */
  .transition-smooth {
    @apply transition-all duration-300 ease-in-out;
  }

  /* Fast color-only transition */
  .transition-colors-fast {
    @apply transition-colors duration-150 ease-out;
  }
}
```

### Hover Animations

```css
@layer components {
  /* Card hover: subtle lift + border brighten */
  .hover-lift {
    @apply transition-all duration-200 ease-out;
  }
  .hover-lift:hover {
    @apply -translate-y-0.5 shadow-md;
  }

  /* Row hover: background change */
  .hover-row {
    @apply transition-colors duration-150 ease-out;
  }
  .hover-row:hover {
    @apply bg-card-elevated/50;
  }

  /* Icon scale on parent hover */
  .group-hover-icon .group:hover & {
    @apply scale-110 transition-transform duration-200;
  }
}
```

### Entry Animations

```css
@layer utilities {
  /* Fade in from below (for new content) */
  .animate-fade-in-up {
    animation: fadeInUp 0.3s ease-out;
  }

  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Slide in from right (for side panels) */
  .animate-slide-in-right {
    animation: slideInRight 0.25s ease-out;
  }

  @keyframes slideInRight {
    from {
      opacity: 0;
      transform: translateX(16px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  /* Slide in from top (for new feed items) */
  .animate-slide-in-top {
    animation: slideInTop 0.3s ease-out;
  }

  @keyframes slideInTop {
    from {
      opacity: 0;
      transform: translateY(-12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Subtle scale-in (for badges, notifications) */
  .animate-scale-in {
    animation: scaleIn 0.2s ease-out;
  }

  @keyframes scaleIn {
    from {
      opacity: 0;
      transform: scale(0.9);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  /* Pulse for active/running indicators */
  .animate-pulse-subtle {
    animation: pulseSubtle 2s ease-in-out infinite;
  }

  @keyframes pulseSubtle {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  /* Skeleton shimmer for loading states */
  .animate-shimmer {
    background: linear-gradient(
      90deg,
      var(--muted) 0%,
      oklch(0.20 0.02 285) 50%,
      var(--muted) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
  }

  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
}
```

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  .animate-fade-in-up,
  .animate-slide-in-right,
  .animate-slide-in-top,
  .animate-scale-in,
  .animate-shimmer {
    animation: none !important;
  }

  .animate-pulse-subtle {
    animation: none !important;
  }

  .hover-lift:hover {
    transform: none !important;
  }

  .transition-interactive,
  .transition-smooth,
  .transition-colors-fast {
    transition-duration: 0.01ms !important;
  }
}
```

---

## 6. Background Updates

### Reduce Orb Intensity

```css
/* UPDATED: Reduce opacity from 0.15 to 0.06 */
.bg-orbs::before,
.bg-orbs::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);      /* CHANGED: was 80px — softer */
  opacity: 0.06;            /* CHANGED: was 0.15 — much more subtle */
  animation: float 80s ease-in-out infinite;  /* CHANGED: was 60s — slower */
}

.bg-orbs::before {
  width: 700px;             /* CHANGED: was 600px — larger but softer */
  height: 700px;
  background: oklch(0.45 0.20 285);  /* CHANGED: slightly dimmer violet */
  top: -250px;
  right: -150px;
}

.bg-orbs::after {
  width: 600px;             /* CHANGED: was 500px */
  height: 600px;
  background: oklch(0.55 0.12 195);  /* CHANGED: slightly dimmer cyan */
  bottom: -200px;
  left: -150px;
  animation-delay: -40s;
}
```

---

## 7. Status Indicator Updates

```css
@layer components {
  /* Status dots — remove glow, add subtle ring */
  .status-dot {
    @apply w-2 h-2 rounded-full ring-2 ring-background;
  }

  .status-dot-success {
    @apply bg-success;
  }
  .status-dot-success.status-dot-active {
    @apply animate-pulse-subtle;
  }

  .status-dot-warning {
    @apply bg-warning;
  }

  .status-dot-error {
    @apply bg-error;
  }

  .status-dot-neutral {
    @apply bg-muted-foreground/40;
  }

  .status-dot-info {
    @apply bg-info;
  }

  /* Larger status indicator for page headers */
  .status-indicator {
    @apply w-2.5 h-2.5 rounded-full ring-2 ring-background;
  }
}
```

---

## 8. Scrollbar Updates

```css
@layer components {
  .scrollbar-thin::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }
  .scrollbar-thin::-webkit-scrollbar-track {
    background: transparent;
  }
  .scrollbar-thin::-webkit-scrollbar-thumb {
    background: oklch(0.25 0.015 285);  /* CHANGED: subtler (was 0.35) */
    border-radius: 3px;
  }
  .scrollbar-thin::-webkit-scrollbar-thumb:hover {
    background: oklch(0.35 0.015 285);  /* CHANGED: (was 0.45) */
  }

  /* NEW: Hidden scrollbar (for mobile-like scrolling) */
  .scrollbar-hidden::-webkit-scrollbar {
    display: none;
  }
  .scrollbar-hidden {
    -ms-overflow-style: none;
    scrollbar-width: none;
  }
}
```

---

## 9. Component Overrides

These are changes to existing shadcn/ui component files.

### 9.1 Card (`client/src/components/ui/card.tsx`)

**Current:**
```tsx
className={cn("rounded-xl border bg-card text-card-foreground shadow-sm", className)}
```

**Change to:**
```tsx
className={cn(
  "rounded-xl border border-border/50 bg-card text-card-foreground",
  "transition-colors duration-200",
  className
)}
```

Remove `shadow-sm` — surfaces should be flat by default. Shadows are added via `.surface-elevated` or `.hover-lift` where needed.

### 9.2 Button (`client/src/components/ui/button.tsx`)

Add `transition-all duration-200 ease-out` to the base styles in `buttonVariants`:

```tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium " +
  "transition-all duration-200 ease-out " +  // ADD THIS
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 " +
  "disabled:pointer-events-none disabled:opacity-50 " +
  "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90 hover:shadow-md",  // ADD hover:shadow-md
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-border/50 bg-transparent hover:bg-card-elevated hover:border-border",  // CHANGED
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-card-elevated/50 hover:text-foreground",  // CHANGED: use card-elevated
        link: "text-primary underline-offset-4 hover:underline",
      },
      // ... sizes unchanged
    },
  }
);
```

### 9.3 Badge (`client/src/components/ui/badge.tsx`)

Update variant styles for better contrast:

```tsx
const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium " +
  "transition-colors duration-150",  // ADD transition
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/15 text-primary",  // CHANGED: was solid bg
        secondary: "border-border/50 bg-secondary/50 text-secondary-foreground",  // CHANGED
        destructive: "border-transparent bg-destructive/15 text-destructive",  // CHANGED
        outline: "border-border/50 text-foreground",
        // NEW variants for status:
        success: "border-transparent bg-success/15 text-success",
        warning: "border-transparent bg-warning/15 text-warning",
        info: "border-transparent bg-info/15 text-info",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);
```

### 9.4 Table (`client/src/components/ui/table.tsx`)

Add hover states to table rows:

```tsx
// TableRow
className={cn(
  "border-b border-border-subtle transition-colors duration-150",  // CHANGED: use border-subtle
  "hover:bg-card-elevated/30",  // ADD hover
  "data-[state=selected]:bg-card-elevated/50",  // CHANGED
  className
)}

// TableHead
className={cn(
  "h-10 px-3 text-left align-middle text-xs font-medium text-muted-foreground uppercase tracking-wider",  // CHANGED: uppercase label style
  className
)}

// TableCell
className={cn(
  "px-3 py-3 align-middle text-sm",  // CHANGED: slightly more padding
  className
)}
```

### 9.5 Tabs (`client/src/components/ui/tabs.tsx`)

Update for cleaner appearance:

```tsx
// TabsList
className={cn(
  "inline-flex h-9 items-center justify-center rounded-lg bg-muted/50 p-1",  // CHANGED: bg-muted/50
  className
)}

// TabsTrigger
className={cn(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium",
  "transition-all duration-200",  // ADD
  "text-muted-foreground hover:text-foreground",
  "data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm",
  className
)}
```

### 9.6 Dialog/Sheet (Side Panel)

These already work well. Add the animation class to Sheet content:

```tsx
// In Sheet usage (not the component file — the consuming code)
<SheetContent className="surface-elevated animate-slide-in-right">
```

### 9.7 Tooltip

```tsx
// TooltipContent
className={cn(
  "surface-elevated z-50 px-3 py-1.5 text-xs text-popover-foreground",  // CHANGED: use surface-elevated
  "animate-scale-in",  // ADD entry animation
  className
)}
```

---

## 10. Glow and Gradient Updates

```css
@layer components {
  /* Reduce glow intensity */
  .glow-primary {
    box-shadow: 0 0 15px oklch(0.65 0.25 285 / 0.15);  /* CHANGED: was 0.3 */
  }
  .glow-accent {
    box-shadow: 0 0 15px oklch(0.75 0.15 195 / 0.15);  /* CHANGED: was 0.3 */
  }

  /* Text gradient (unchanged) */
  .text-gradient {
    @apply bg-clip-text text-transparent bg-gradient-to-r from-primary to-accent;
  }

  /* NEW: Subtle gradient border for featured/highlighted items */
  .gradient-border-subtle {
    position: relative;
  }
  .gradient-border-subtle::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 1px;
    background: linear-gradient(135deg, oklch(0.65 0.25 285 / 0.3), oklch(0.75 0.15 195 / 0.15));
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    pointer-events: none;
  }
}
```

---

## 11. Implementation Checklist

This is the exact sequence of changes to make.

### Step 1: Update CSS Variables
- [ ] **File:** `client/src/index.css` — `:root` block
- [ ] Change `--background` from `oklch(0.11 0.02 285)` to `oklch(0.09 0.015 285)`
- [ ] Change `--foreground` from `oklch(0.98 0.005 285)` to `oklch(0.95 0.005 285)`
- [ ] Change `--card` from `oklch(0.16 0.015 285)` to `oklch(0.12 0.012 285)`
- [ ] Change `--card-foreground` to `oklch(0.95 0.005 285)`
- [ ] Add `--card-elevated: oklch(0.14 0.015 285)`
- [ ] Change `--popover` to `oklch(0.14 0.015 285)`
- [ ] Change `--secondary` from `oklch(0.22 0.03 285)` to `oklch(0.18 0.02 285)`
- [ ] Change `--muted` from `oklch(0.20 0.02 285)` to `oklch(0.15 0.015 285)`
- [ ] Change `--muted-foreground` from `oklch(0.65 0.02 285)` to `oklch(0.55 0.015 285)`
- [ ] Change `--border` from `oklch(0.30 0.02 285)` to `oklch(0.22 0.015 285)`
- [ ] Add `--border-subtle: oklch(0.17 0.01 285)`
- [ ] Change `--input` from `oklch(0.25 0.02 285)` to `oklch(0.18 0.015 285)`
- [ ] Change `--radius` from `0.75rem` to `0.625rem`
- [ ] Update sidebar colors as specified
- [ ] Add `--info: oklch(0.65 0.15 240)`

### Step 2: Update Theme Mappings
- [ ] **File:** `client/src/index.css` — `@theme inline` block
- [ ] Add `--color-card-elevated`, `--color-border-subtle`, `--color-info`, `--color-success`, `--color-warning`, `--color-error`

### Step 3: Replace Surface Classes
- [ ] **File:** `client/src/index.css` — `@layer components`
- [ ] Remove `.glass` and `.glass-subtle` definitions
- [ ] Add `.surface`, `.surface-elevated`, `.surface-interactive`, `.surface-inset`
- [ ] Add new `.glass` definition (reserved for overlays only)

### Step 4: Add Typography Utilities
- [ ] **File:** `client/src/index.css` — `@layer utilities`
- [ ] Add `.text-heading-1`, `.text-heading-2`, `.text-heading-3`
- [ ] Add `.text-body`, `.text-body-lg`
- [ ] Add `.text-label`, `.text-caption`
- [ ] Add `.text-mono`

### Step 5: Add Spacing Utilities
- [ ] **File:** `client/src/index.css` — `@layer utilities`
- [ ] Add `.page-padding`, `.section-gap`, `.card-padding`, `.card-padding-compact`
- [ ] Add `.grid-gap`, `.stack-xs` through `.stack-xl`
- [ ] Update `.container` media queries

### Step 6: Add Animation Utilities
- [ ] **File:** `client/src/index.css` — `@layer utilities`
- [ ] Add `.transition-interactive`, `.transition-smooth`, `.transition-colors-fast`
- [ ] Add `.animate-fade-in-up`, `.animate-slide-in-right`, `.animate-slide-in-top`
- [ ] Add `.animate-scale-in`, `.animate-pulse-subtle`, `.animate-shimmer`
- [ ] Add `.hover-lift`, `.hover-row`
- [ ] Add `@media (prefers-reduced-motion: reduce)` block

### Step 7: Update Background Orbs
- [ ] **File:** `client/src/index.css` — `.bg-orbs` rules
- [ ] Reduce opacity from 0.15 to 0.06
- [ ] Increase blur from 80px to 100px
- [ ] Slow animation from 60s to 80s
- [ ] Adjust sizes and positions as specified

### Step 8: Update Status Indicators
- [ ] **File:** `client/src/index.css` — status dot classes
- [ ] Remove glow shadows from status dots
- [ ] Add `ring-2 ring-background` to status dots
- [ ] Add `.status-dot-info`, `.status-dot-active`
- [ ] Add `.status-indicator` (larger variant)

### Step 9: Update Scrollbar
- [ ] **File:** `client/src/index.css` — scrollbar classes
- [ ] Reduce thumb color intensity
- [ ] Add `.scrollbar-hidden` class

### Step 10: Update Glow/Gradient
- [ ] **File:** `client/src/index.css`
- [ ] Reduce `.glow-primary` and `.glow-accent` opacity
- [ ] Replace `.gradient-border` with `.gradient-border-subtle`

### Step 11: Override shadcn Components
- [ ] **File:** `client/src/components/ui/card.tsx` — remove shadow, add transition, use border/50
- [ ] **File:** `client/src/components/ui/button.tsx` — add transition-all, update variant hover states
- [ ] **File:** `client/src/components/ui/badge.tsx` — update variants, add success/warning/info
- [ ] **File:** `client/src/components/ui/table.tsx` — add row hover, update head style, use border-subtle
- [ ] **File:** `client/src/components/ui/tabs.tsx` — update list bg, trigger transition
- [ ] **File:** `client/src/components/ui/tooltip.tsx` — use surface-elevated, add animate-scale-in

### Step 12: Update Light Theme (if keeping)
- [ ] **File:** `client/src/index.css` — `.light` block
- [ ] Update to match new token structure (add card-elevated, border-subtle, etc.)
- [ ] OR remove `.light` block if deferring light mode

---

## 12. Verification

After completing all steps:

1. **Visual check all existing pages:**
   - [ ] Monitoring dashboard renders correctly
   - [ ] Registry page renders correctly
   - [ ] Chat page renders correctly
   - [ ] Workflows page renders correctly

2. **Interaction check:**
   - [ ] All buttons have visible hover/active states
   - [ ] Cards have hover transitions
   - [ ] Tooltips appear with scale-in animation
   - [ ] Sidebar navigation highlights correctly
   - [ ] Mobile navigation works

3. **Contrast check:**
   - [ ] Body text (foreground on background): ratio > 7:1
   - [ ] Muted text (muted-foreground on background): ratio > 4.5:1
   - [ ] Border visibility: borders are visible but not harsh
   - [ ] Status dot colors distinguishable

4. **Performance check:**
   - [ ] No layout shift on load
   - [ ] Animations run at 60fps
   - [ ] No flash of unstyled content
   - [ ] Reduced motion preference respected

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `client/src/index.css` | Complete overhaul of variables, surfaces, utilities, animations |
| `client/src/components/ui/card.tsx` | Remove shadow, add transition, update border |
| `client/src/components/ui/button.tsx` | Add transitions, update hover states |
| `client/src/components/ui/badge.tsx` | Update variants, add status variants |
| `client/src/components/ui/table.tsx` | Add row hover, update head/cell styling |
| `client/src/components/ui/tabs.tsx` | Update list background, trigger transitions |
| `client/src/components/ui/tooltip.tsx` | Use surface-elevated, add animation |

**Total: 7 files modified**
