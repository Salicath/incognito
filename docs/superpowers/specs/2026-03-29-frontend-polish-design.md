# Frontend Polish — Design Spec

**Date:** 2026-03-29
**Status:** Approved

## Scope

Three user-visible improvements to the React/TypeScript frontend:

1. **Dark mode completion** — add `dark:` Tailwind variants to all pages/components
2. **Replace browser prompt()/alert()** — inline UI for actions requiring user input
3. **Loading states** — add spinners to all async buttons

## 1. Dark Mode Completion

### Problem

The app has a working dark mode toggle (in Layout sidebar) but only ~2% of components have `dark:` classes. White cards, light borders, and hardcoded text colors look broken when dark mode is active.

### Existing Infrastructure

- `index.css` defines CSS custom properties for dark mode (surface colors, borders, text)
- `tailwind.config.js` uses `darkMode: "class"` strategy
- `Layout.tsx` manages the `dark` class on `document.documentElement`
- `Dashboard.tsx` has 4 inline dark mode classes (the only page with any)

### Fix

Add `dark:` variants to every page and component. The pattern is consistent:

| Light Class | Dark Variant |
|------------|-------------|
| `bg-white` | `dark:bg-gray-900` |
| `border-gray-200` | `dark:border-gray-700` |
| `text-gray-900` | `dark:text-gray-100` |
| `text-gray-500` | `dark:text-gray-400` |
| `text-gray-600` | `dark:text-gray-300` |
| `bg-gray-50` | `dark:bg-gray-800` |
| `bg-gray-100` | `dark:bg-gray-800` |
| `divide-gray-100` | `dark:divide-gray-800` |
| `shadow-sm` | `dark:shadow-none` or keep |

Status badges, colored alerts (green/red/orange/yellow/blue backgrounds), and the gradient hero card already work because they use non-gray colors that are readable in both modes.

### Files

Every file in `frontend/src/pages/` and `frontend/src/components/`:
- `Dashboard.tsx` — extend existing dark classes to remaining elements
- `Requests.tsx` — cards, table rows, filter tabs
- `RequestDetail.tsx` — header card, actions card, DPA complaint card, timeline, email thread
- `Brokers.tsx` — search bar, broker list, badges
- `Scan.tsx` — scan cards, result lists, progress bars
- `Settings.tsx` — all settings cards, form inputs
- `SetupWizard.tsx` — wizard steps, form inputs
- `Layout.tsx` — already mostly styled, verify completeness
- `StatusBadge.tsx` — verify badge colors work in dark mode
- `ProgressRing.tsx` — SVG colors (already uses props, should be fine)
- `EmailThread.tsx` — outbound/inbound email cards

### Input Styling

Form inputs already have dark mode styles via CSS custom properties in `index.css`. The `inputClass` pattern used in Settings.tsx needs `dark:` variants added:

```
dark:bg-gray-800 dark:border-gray-600 dark:text-gray-100
```

## 2. Replace Browser Dialogs

### Problem

Three places use browser `prompt()` or `alert()` instead of inline UI:

1. **RequestDetail.tsx** — "Mark Acknowledged" opens `prompt("Enter the broker's response:")`
2. **RequestDetail.tsx** — "Mark Refused" opens `prompt("Reason for refusal:")`
3. **Brokers.tsx** — after creating a request, shows `alert("Request created...")`

### Fix

**RequestDetail:** Replace both `prompt()` calls with an expandable inline form. When the user clicks "Mark Acknowledged" or "Mark Refused", show a text area below the button with a submit/cancel pair. State: `pendingAction: { type: "acknowledged" | "refused", text: string } | null`.

**Brokers:** Replace `alert()` with an inline success message that auto-dismisses after 3 seconds. Use the same green message pattern as Settings.tsx.

### Files

- `frontend/src/pages/RequestDetail.tsx` — add inline action form
- `frontend/src/pages/Brokers.tsx` — add inline success feedback

## 3. Loading States

### Problem

Many async buttons show no visual feedback. The user clicks and waits with no indication of progress.

### Current State

Some pages already have loading state patterns (e.g., Dashboard has `blastLoading`, `sendLoading`). But many buttons don't show a spinner even when they track loading state — they just disable via `disabled={!!actionLoading}`.

### Fix

Add `Loader2` spinner (from lucide-react, already imported in most files) to all async buttons when their operation is in progress. The pattern:

```tsx
<button disabled={loading}>
  {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
  Label
</button>
```

### Files

- `RequestDetail.tsx` — action buttons (mark sent, acknowledged, completed, etc.)
- `Brokers.tsx` — Art. 15 / Art. 17 buttons
- `Requests.tsx` — send button on individual requests

## Testing

No backend changes. Verification:
- `npm run build` must succeed (TypeScript compilation)
- Visual check in both light and dark mode
- Verify all interactive elements still work after dialog replacements

## Out of Scope

- Accessibility / ARIA labels
- Settings.tsx state refactoring
- Component library / design system
- Pagination on list views
- Toast/notification system (use inline messages instead)
