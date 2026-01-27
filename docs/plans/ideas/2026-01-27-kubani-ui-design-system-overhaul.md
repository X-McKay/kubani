# Kubani UI Design System Overhaul

**Date:** 2026-01-27
**Status:** Idea
**Inspiration:** [Factory.ai](https://factory.ai/) dark mode aesthetic
**Approach:** Design System Overhaul (comprehensive)

---

## Executive Summary

Modernize Kubani's UI by creating a formal design system layer that adopts Factory.ai's refined dark mode aesthetic while preserving Kubani's violet/cyan color identity. The focus is on:

1. **Refined surfaces** — Less glass effect, more matte dark panels with subtle borders
2. **Micro-animations** — Smooth transitions, hover effects, and visual feedback
3. **Spacing & hierarchy** — Generous whitespace, clearer visual separation

Secondary goals include low-effort feature additions that deepen kubani service integration.

---

## Part 1: Visual Design Specifications

### 1.1 Surface Treatment Changes

**Current (Glass Morphism):**
```css
.glass {
  @apply bg-card/60 backdrop-blur-xl border border-white/10 shadow-xl;
}
```

**Proposed (Refined Dark):**
```css
/* Primary surface - matte with subtle border */
.surface {
  @apply bg-card border border-border/50;
}

/* Elevated surface - slight lift without heavy blur */
.surface-elevated {
  @apply bg-card/95 border border-border/60 shadow-lg;
}

/* Interactive surface - for cards, list items */
.surface-interactive {
  @apply bg-card border border-border/50
         hover:bg-card/80 hover:border-border
         transition-all duration-200;
}

/* Keep glass for special elements only (modals, mobile nav) */
.glass {
  @apply bg-card/80 backdrop-blur-md border border-border/40;
}
```

**Key Changes:**
- Remove `backdrop-blur-xl` from most surfaces (keep for overlays only)
- Use solid `bg-card` instead of `bg-card/60`
- Subtle borders with `border-border/50` instead of `border-white/10`
- Reserve glass effect for modals, sheets, and mobile navigation

### 1.2 Color Token Adjustments

Keep existing OKLCH palette but adjust surface colors for better contrast:

```css
:root {
  /* Existing - keep unchanged */
  --primary: oklch(0.65 0.25 285);      /* Vibrant violet */
  --accent: oklch(0.75 0.15 195);       /* Cyan */

  /* Adjusted surfaces - slightly higher lightness for layering */
  --background: oklch(0.09 0.015 285);  /* Darker base (was 0.11) */
  --card: oklch(0.12 0.012 285);        /* Card surface (was 0.16) */
  --card-elevated: oklch(0.14 0.015 285); /* NEW: elevated cards */

  /* Refined borders */
  --border: oklch(0.22 0.015 285);      /* More visible (was 0.30) */
  --border-subtle: oklch(0.18 0.01 285); /* NEW: subtle separator */

  /* Text hierarchy */
  --foreground: oklch(0.95 0.005 285);  /* Slightly softer white */
  --muted-foreground: oklch(0.55 0.015 285); /* Better contrast */
}
```

### 1.3 Typography Scale

Adopt Factory.ai's generous spacing approach:

```css
@theme inline {
  /* Existing fonts - keep */
  --font-sans: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* NEW: Typography scale */
  --text-xs: 0.75rem;     /* 12px */
  --text-sm: 0.875rem;    /* 14px - Factory's base */
  --text-base: 1rem;      /* 16px */
  --text-lg: 1.125rem;    /* 18px */
  --text-xl: 1.25rem;     /* 20px */
  --text-2xl: 1.5rem;     /* 24px */
  --text-3xl: 2rem;       /* 32px */

  /* Line heights - slightly looser */
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;
}
```

---

## Part 2: Animation & Transition System

### 2.1 Base Transitions

Factory.ai uses consistent `duration-200` and `duration-300` patterns:

```css
@layer utilities {
  /* Standard transitions */
  .transition-base {
    @apply transition-all duration-200 ease-out;
  }

  .transition-smooth {
    @apply transition-all duration-300 ease-in-out;
  }

  .transition-colors-fast {
    @apply transition-colors duration-150 ease-out;
  }

  /* Disable transitions during theme switch (Factory pattern) */
  .disable-transitions * {
    transition: none !important;
  }
}
```

### 2.2 Hover Animations

```css
@layer components {
  /* Expanding underline (Factory signature) */
  .hover-underline {
    @apply relative;
  }
  .hover-underline::after {
    content: '';
    @apply absolute bottom-0 left-0 w-0 h-px bg-current
           transition-all duration-300 ease-in-out;
  }
  .hover-underline:hover::after {
    @apply w-full;
  }

  /* Card hover lift */
  .hover-lift {
    @apply transition-transform duration-200;
  }
  .hover-lift:hover {
    @apply -translate-y-0.5;
  }

  /* Icon hover scale */
  .hover-icon-scale:hover svg {
    @apply scale-110 transition-transform duration-200;
  }
}
```

### 2.3 Loading States

```css
@layer components {
  /* Progress slide (Factory pattern) */
  .progress-slide {
    animation: progress-slide 2s linear infinite;
  }

  @keyframes progress-slide {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
  }

  /* Skeleton shimmer */
  .skeleton {
    @apply bg-muted animate-pulse rounded;
  }

  /* Fade in on load */
  .animate-fade-in {
    animation: fade-in 0.3s ease-out;
  }

  @keyframes fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
}
```

---

## Part 3: Spacing System

### 3.1 Layout Spacing Scale

Adopt Factory's generous spacing (their patterns: `gap-x-4 lg:gap-x-6`, `my-20`):

```css
@layer utilities {
  /* Section spacing */
  .section-spacing {
    @apply py-12 lg:py-20;
  }

  /* Card internal padding */
  .card-padding {
    @apply p-4 lg:p-6;
  }

  /* Grid gaps */
  .grid-gap {
    @apply gap-4 lg:gap-6;
  }

  /* Stack spacing */
  .stack-sm { @apply space-y-2; }
  .stack-md { @apply space-y-4; }
  .stack-lg { @apply space-y-6; }
  .stack-xl { @apply space-y-8; }
}
```

### 3.2 Container Updates

```css
@layer components {
  .container {
    width: 100%;
    margin-left: auto;
    margin-right: auto;
    padding-left: 1rem;    /* 16px mobile */
    padding-right: 1rem;
  }

  @media (min-width: 640px) {
    .container {
      padding-left: 1.5rem;  /* 24px tablet */
      padding-right: 1.5rem;
    }
  }

  @media (min-width: 1024px) {
    .container {
      padding-left: 2.25rem;  /* 36px - more generous */
      padding-right: 2.25rem;
      max-width: 1400px;
    }
  }

  @media (min-width: 1536px) {
    .container {
      padding-left: 3rem;    /* 48px - Factory-like */
      padding-right: 3rem;
    }
  }
}
```

### 3.3 Responsive Grid

Factory uses 4-col mobile → 12-col desktop:

```css
@layer utilities {
  /* Responsive grid utility */
  .responsive-grid {
    @apply grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4;
  }

  /* Full 12-column grid for complex layouts */
  .grid-12 {
    @apply grid grid-cols-4 lg:grid-cols-12 gap-x-4 lg:gap-x-6;
  }
}
```

---

## Part 4: Component Updates

### 4.1 DashboardLayout Updates

**File:** `client/src/components/DashboardLayout.tsx`

| Change | Current | Proposed |
|--------|---------|----------|
| Sidebar surface | `glass border-r border-white/10` | `surface border-r border-border` |
| Nav item hover | `hover:bg-white/5` | `hover:bg-card/80 transition-base` |
| Active nav | `bg-primary/10 border-primary/20` | `bg-primary/15 border-primary/30` |
| Logo section | `border-b border-white/10` | `border-b border-border-subtle` |
| Collapse animation | `duration-300` | Keep (already good) |
| Background orbs | Keep but reduce opacity | `opacity: 0.08` (was 0.15) |

**Additional changes:**
- Add `transition-base` to all interactive elements
- Increase padding in nav items: `py-2.5` → `py-3`
- Add hover underline effect to nav labels

### 4.2 Card Component Override

**File:** `client/src/components/ui/card.tsx` (shadcn override)

```tsx
const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        // Updated styling
        "rounded-xl border border-border/50 bg-card",
        "transition-all duration-200",
        "hover:border-border/80",
        className
      )}
      {...props}
    />
  )
)
```

### 4.3 Button Hover States

Add micro-animation to existing button variants:

```tsx
// In button.tsx variants
const buttonVariants = cva(
  // Add base transition
  "transition-all duration-200 ease-out",
  {
    variants: {
      variant: {
        default: "bg-primary hover:bg-primary/90 hover:shadow-md",
        ghost: "hover:bg-accent/10 hover:text-accent-foreground",
        // ... existing variants with added hover effects
      }
    }
  }
)
```

### 4.4 Page-Level Updates

**Monitoring.tsx:**
- Replace `.glass` cards with `.surface`
- Add `animate-fade-in` to metric cards on load
- Increase grid gap: `gap-4` → `gap-6`

**Registry.tsx:**
- Add `hover-lift` to agent/skill cards
- Expand tab content area padding
- Add skeleton loading states

**Chat.tsx:**
- Smoother message appearance animations
- Tool call blocks use `.surface-elevated`
- Input area uses `.surface` with focus ring

**Workflows.tsx:**
- Table rows with `hover:bg-card/60` transition
- Status badges with subtle pulse on "running"

---

## Part 5: Low-Effort Feature Opportunities

### 5.1 Deeper Kubani Integration (Option C)

These features leverage existing backend capabilities with minimal frontend effort:

| Feature | Effort | Backend Ready? | Impact |
|---------|--------|----------------|--------|
| **Live workflow status** | Low | Yes (Temporal MCP) | Show active Temporal workflows on dashboard |
| **Agent heartbeat indicator** | Low | Yes (Registry) | Real-time agent health dots in Registry |
| **Recent learnings feed** | Medium | Partial (Learning system) | Display recent skill proposals in sidebar |
| **MCP server status** | Low | Yes (MCP servers) | Health indicators for connected MCP servers |

**Quick Win: Agent Status Pills**

Add to Registry page header:
```tsx
<div className="flex gap-2">
  {agents.map(a => (
    <Tooltip key={a.id}>
      <TooltipTrigger>
        <div className={cn(
          "w-2 h-2 rounded-full transition-colors",
          a.status === 'healthy' && "bg-success animate-pulse-slow",
          a.status === 'busy' && "bg-warning",
          a.status === 'offline' && "bg-muted"
        )} />
      </TooltipTrigger>
      <TooltipContent>{a.name}: {a.status}</TooltipContent>
    </Tooltip>
  ))}
</div>
```

### 5.2 Factory-Inspired Feature Ideas (Option B)

| Feature | Factory Equivalent | Kubani Adaptation | Effort |
|---------|-------------------|-------------------|--------|
| **Autonomy slider** | Auto-run levels | Agent confidence threshold in Chat | Medium |
| **Execution mode toggle** | Headless/interactive | "Run in background" option | Medium |
| **Cost tracking** | Usage metrics | Token/API call counts | Low |
| **Model selector** | Multi-provider | Switch LLM models in Chat | Low |

**Quick Win: Model Selector in Chat**

Already have model data in Registry. Add dropdown to Chat page:
```tsx
<Select value={selectedModel} onValueChange={setSelectedModel}>
  <SelectTrigger className="w-48">
    <SelectValue placeholder="Select model" />
  </SelectTrigger>
  <SelectContent>
    {models.map(m => (
      <SelectItem key={m.id} value={m.id}>
        {m.name} ({m.context_length}k)
      </SelectItem>
    ))}
  </SelectContent>
</Select>
```

---

## Part 6: Implementation Phases

### Phase 1: Design Tokens & Base Styles (1-2 days)

**Files to modify:**
- `client/src/index.css` — All CSS variable and utility changes

**Changes:**
1. Update color tokens (surface colors, borders)
2. Add transition utilities
3. Add animation utilities
4. Update container spacing
5. Reduce background orb opacity
6. Add new surface classes

**Validation:** Visual inspection of all pages, no functional changes

### Phase 2: Component Library Updates (2-3 days)

**Files to modify:**
- `client/src/components/ui/card.tsx`
- `client/src/components/ui/button.tsx`
- `client/src/components/ui/badge.tsx`
- `client/src/components/ui/table.tsx`
- `client/src/components/DashboardLayout.tsx`

**Changes:**
1. Update Card component styling
2. Add hover transitions to Button
3. Update Badge styling for consistency
4. Add row hover to Table
5. Refine DashboardLayout surfaces and spacing

**Validation:** Component storybook review (if available), manual testing

### Phase 3: Page-Level Polish (2-3 days)

**Files to modify:**
- `client/src/pages/Monitoring.tsx`
- `client/src/pages/Registry.tsx`
- `client/src/pages/Chat.tsx`
- `client/src/pages/Workflows.tsx`

**Changes:**
1. Replace glass classes with surface classes
2. Add fade-in animations to dynamic content
3. Increase spacing per new system
4. Add hover effects to interactive elements
5. Improve loading states

**Validation:** Full page walkthroughs, responsive testing

### Phase 4: Quick-Win Features (1-2 days)

**Files to modify:**
- `client/src/pages/Chat.tsx` — Model selector
- `client/src/pages/Registry.tsx` — Agent status pills
- `client/src/components/DashboardLayout.tsx` — MCP status indicators

**Changes:**
1. Add model selector dropdown to Chat
2. Add live agent status indicators
3. Add MCP server health to sidebar (if API available)

**Validation:** Feature testing with real/mock data

---

## Part 7: Success Criteria

### Visual Quality
- [ ] All surfaces use consistent matte dark treatment
- [ ] Hover states on all interactive elements
- [ ] Smooth 200-300ms transitions throughout
- [ ] No jarring visual changes on interaction
- [ ] Background orbs subtle but present

### Spacing & Hierarchy
- [ ] Increased padding on all cards and sections
- [ ] Clear visual separation between content areas
- [ ] Consistent grid gaps across pages
- [ ] Readable typography with good line height

### Performance
- [ ] No layout shift on page load
- [ ] Animations at 60fps
- [ ] First contentful paint < 1.5s
- [ ] No visible transition-induced flickering

### Accessibility
- [ ] All interactive elements remain keyboard navigable
- [ ] Color contrast meets WCAG AA
- [ ] Focus states visible and consistent
- [ ] Reduced motion respected

---

## Part 8: Files Changed Summary

| Category | Files | Changes |
|----------|-------|---------|
| **Design Tokens** | `index.css` | Color, spacing, animation utilities |
| **Components** | 4-5 UI components | Surface and hover updates |
| **Layout** | `DashboardLayout.tsx` | Spacing, surfaces, transitions |
| **Pages** | 4 page files | Apply new design system |
| **Features** | 2-3 files | Model selector, status indicators |

**Estimated Total:** 12-15 files modified over 6-10 days

---

## Appendix: Reference Screenshots Needed

Before implementation, capture current state screenshots:
1. Monitoring dashboard (desktop + mobile)
2. Registry page (all tabs)
3. Chat interface (with tool calls visible)
4. Workflows table
5. Sidebar (expanded + collapsed)

Compare against Factory.ai's dark mode for reference during implementation.

---

## Next Steps

1. **Review this plan** — Validate approach and priorities
2. **Move to drafts/** — When ready to refine details
3. **Create implementation branch** — `feature/ui-design-system-overhaul`
4. **Phase 1 execution** — Start with index.css changes
