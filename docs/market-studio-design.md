# Market Studio design contract

Order 022 applies Yellow's compact operational UI language to the existing CompSet Studio. The [approved concept](design/market-studio-concept.png) establishes the intended hierarchy: a quiet pale shell, warm yellow selected state, compact action ribbon, a large map beside a candidate list, and a concise area summary. The screenshot is directional. Its city, dates, imagery, logos, and counts are illustrative; the application must render saved, attributable records only.

## Screen structure

- The left rail keeps the existing STR/hotel choice and workspace navigation visible on desktop. A warm yellow capsule marks the current destination. On mobile, the existing bottom navigation and mode switch remain the entry points to the same functions.
- The header gives the selected portfolio or property first place. Coverage metrics form a narrow evidence strip; source time remains explicitly labelled. Filters sit in a grouped ribbon immediately above the working canvas.
- Comparison and calendar views use compact table headers, aligned numeric values, clear row boundaries, and a persistent detail inspector. The inspector becomes a mobile sheet without removing evidence or actions.
- Hotel rate/calendar lanes follow Yellow's movement-table structure as well as its palette: a segmented view ribbon, labelled search/count and table controls, sticky column headers and property identity, compact rows, and a source/offer inspector. A narrow day cell may summarize offers, but the selected date must open every available source detail and condition. A missing quote stays unknown or unavailable according to its actual source state.
- In the map view, the map receives roughly 65% of the desktop workspace and the candidates occupy the remaining rail. Candidate rows present identity first, then saved decision, observed distance, and evidence. The observed-area summary runs across the bottom. At narrower widths, the map, candidates, and summary stack in reading order.
- Circle, polygon, move, and resize controls have a visible armed state. Apply is the prominent action when a polygon draft is valid. Undo, Cancel, and Clear remain separate operations. Map input targets and other controls remain at least 44 CSS pixels tall.

## Color and type

The workbench uses near-white surfaces (`#f7f7f4` background, white canvas), charcoal text (`#171715` for headings), hairline borders (`#e4e3dc`), and yellow (`#f6c900`) for selection and primary area actions. Manrope is preferred when available locally, with Segoe UI and Arial fallbacks; no remote font request is required. Quoted, indicative, unavailable, unknown, restricted, error, and success evidence keep distinct semantic treatments. Yellow never implies a quote is available or a candidate is selected by a saved comparison decision.

## Interaction and truth boundaries

The map area is a view filter over located saved candidates. Drawing, applying, cancelling, or clearing it must not change collection scope, saved candidate decisions, rate evidence, or source identities. Unknown coordinates stay unknown; unknown prices do not become zero, and unavailable inventory does not become booked inventory. The map list remains usable if map tiles fail. Keyboard focus is visible; reduced-motion users receive no necessary animation. Every active selection is conveyed by label or state as well as color.

The existing DOM and data contracts are retained. CSS can arrange `dw-map-view` children in a grid without moving their source order. The observed candidate table keeps its semantic table and accessible region label even when styled as compact rows in the desktop rail. At the mobile breakpoint, the source order remains the reading order.

Yellow's current `MovementTableControls` reference uses one shared editor surface for Filter, Sort and Columns, with search and a visible result count above it. Its segmented ribbon uses a neutral track, 44px buttons and a white selected capsule with a yellow outline. CompSet's rate table places search, count, Filter, Sort and Columns together; Filter and Columns share one editor surface over real saved source, room, meal and cancellation criteria. Horizontal table overflow preserves data columns, and the detail route remains available from each recorded offer row.

## Validation targets

Review the live `http://127.0.0.1:8765/` at desktop and mobile widths. Confirm both property modes, each workspace tab, map circle and polygon editing, candidate inspection, long labels, empty and missing-location states, table overflow, inspector dismissal, keyboard focus, and 44px control targets. Browser appearance and executable workflow checks are separate evidence from this design note.
