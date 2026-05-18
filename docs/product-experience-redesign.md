# Refactor V2 Product Experience Redesign

## 1. Product positioning

Refactor V2 is no longer a single-page demo. It is a multi-terminal trading workspace covering:

- market observation
- live trading execution
- AI and strategy research
- account and broker operations
- platform administration

This means the project needs a product-level experience model instead of page-by-page visual fixes.

## 2. Primary user roles

- Trader: wants to move from market context to order execution with minimum friction.
- Research user: wants to compare AI insight, strategy logic and backtest evidence.
- Operator / admin: wants stable access to health, users, tasks and configuration.
- Mobile user: wants short-path actions, readable hierarchy and fewer long-scroll dead zones.

## 3. Core requirements extracted from current structure

From the current routes and view inventory, the product has four main requirement clusters:

1. Workspace cluster
   Dashboard, profile, notifications, broker connection.
   Requirement: a clear landing surface that tells the user what matters now.

2. Market cluster
   Market data, stock pool, symbol detail, finance news, recommendations.
   Requirement: discovery, filtering and drill-down should feel like one continuous workflow.

3. Trading cluster
   Trading, positions, orders, risk.
   Requirement: execution context, order feedback and account state must remain visible and coherent.

4. Analysis / platform cluster
   AI analysis, strategy, backtest, settings, scheduler, user management.
   Requirement: heavy information pages need stronger structure and clearer section hierarchy.

## 4. Current experience problems

- Global shell quality is uneven. The app has strong pages, but the top-level chrome does not consistently signal subsystem, context and next action.
- Navigation density is high. Users must mentally parse many entries before reaching the right workflow.
- Desktop and mobile styles are closer than they should be. Mobile still inherits desktop density in several flows.
- Card rhythm is inconsistent. Similar information blocks use different spacing and visual weight.
- Page headers do not consistently frame why the user is on a page and what the primary action is.

## 5. Redesign principles

- One shell, many workflows.
  The app should feel like one product, not a collection of pages.

- Context before detail.
  Every page needs a compact summary layer before deeper data tables and forms.

- Mobile first for dense flows.
  Short actions, stronger grouping and cleaner vertical rhythm should drive the compact layout.

- Visual weight should follow business priority.
  Execution and health signals must stand out more than decorative content.

- Reuse patterns aggressively.
  Shared page headers, card surfaces, hero blocks and grouped navigation reduce future maintenance cost.

## 6. IA and interaction direction

- Keep the existing route map, but present it through subsystem-led navigation.
- Make subsystem identity visible in the shell.
- Reduce the number of visual jumps between header, tabs, side navigation and content body.
- Use page hero areas for current context, not generic banners.
- Keep tables and charts secondary to quick decision context on small screens.

## 7. Changes implemented in this round

- Added a unified experience stylesheet for shell, hero, page header and card rhythm.
- Reworked the main layout atmosphere and content shell to improve product identity.
- Enhanced the desktop header with context chips and page-level summary text.
- Added a sidebar brief block so users can understand subsystem scope at a glance.
- Generated a shared macOS icon pipeline so desktop packaging matches the rest of the product brand.

## 8. Recommended next iterations

- Convert repeated page header patterns into a dedicated reusable Vue component.
- Extract hero sections used by Dashboard, Positions, StockPool and Recommendations into shared building blocks.
- Introduce a command/search palette for desktop.
- Add task-focused empty states for trading, market and analysis flows.
- Create a shared analytics layer for measuring which entry points and actions are actually used.
