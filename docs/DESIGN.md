# Design

## Direction
A modern, calm desktop web app in Microsoft Fluent 2 / Windows 11 style. It should feel like a native professional Windows administration tool, not a SaaS dashboard.

## Principles
- Neutral light/dark surfaces with restrained depth.
- Clear hierarchy and compact controls.
- One accent color used sparingly.
- Dashboard summary areas may use subtle elevated cards.
- Real work areas (Docker tables, groups, schedules, editors, logs) stay flat, dense and space-efficient.
- No decorative gradients, glassmorphism, oversized hero cards or marketing patterns.
- Status is never communicated by color alone.

## Navigation
Desktop sidebar:
1. Home
2. Containers
3. Groups
4. Schedules
5. NAS
6. Logs
7. Settings

Home is a compact control dashboard with Docker/NAS status, next schedule, latest error, favorite group quick actions and active operations.

## Theme
Mandatory three-state control:
- System — default
- Dark
- Light

Persist the explicit choice. `System` follows `prefers-color-scheme` and reacts live to OS changes. Theme changes apply without reload.

## Density
Compact is the default. Tables are preferred for container and schedule work. Cards are not used as generic wrappers for every section.

## Responsive behavior
Desktop-first but fully usable on tablet/mobile. Collapse the sidebar; preserve primary actions. Dense tables may progressively hide secondary columns or switch to structured rows where necessary.

## Accessibility
- Keyboard-operable controls and navigation.
- Visible focus states.
- Tooltips/accessible names for icon-only actions.
- Sufficient contrast in light and dark themes.
- Motion is subtle and functional; respect reduced-motion preferences.
