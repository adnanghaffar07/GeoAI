# Rough Timeline (P1)

**Status:** First estimate, 2026-10-14. **Updated 2026-10-28** with what actually happened (section at the end).

## In plain words

This is a **rough guess** of how long each stage takes, for **one developer working full-time** with AI help.
It is a range, not a promise. The real time depends mostly on how quickly the customer answers the questions in `03-requirements/partner-inputs.md`.

| Phase | What happens | Estimate |
|-------|--------------|----------|
| P1 | Finish planning (this phase) | done this week |
| P2 | Design the database, the API list, and the screens | 1–2 weeks |
| P3 | Login, organizations, permissions (foundation already done) | 2–3 weeks |
| P4 | Projects and photo upload | 2–3 weeks |
| P5 | AI analysis jobs (with the test detector) | 1–2 weeks |
| P6 | Map, list, and review screens | 3–4 weeks |
| P7 | Priority, inspections, and reports | 2–3 weeks |
| P9 | Full testing and fixes | 2 weeks |
| P10 | Put the pilot online for the customer | 1–2 weeks |
| P11 | Handover documents | 1 week |
| **Total (main line)** | | **about 15–22 weeks (4–5 months)** |

**P8 (training the real AI)** runs alongside the main line. It needs the customer's photos, training permission, and a qualified reviewer first.
After those arrive, expect **4–8 weeks** of labelling, training, and testing. Until then the app runs with the test detector, so this does not block the main line.

## What could make it longer

- Slow answers from the customer, especially the 3 BLOCKED inputs.
- No qualified reviewer available to label photos.
- Part-time work instead of full-time.
- Scope added during the build (handled through change control in `02-process/development-model.md`).

## What could make it shorter

- Skipping the "if time allows" features (road suggestions, duplicate merging).
- Fast, complete answers from the customer.

## What actually happened (updated 2026-10-28)

The main line went much faster than estimated: P2–P7 were built between 2026-10-14 and 2026-10-15, then improved through 2026-10-28.

| Phase | Estimate | Actual |
|-------|----------|--------|
| P1–P2 | 1–2 weeks | 2026-10-13 to 10-14 |
| P3–P7 | 10–15 weeks | Built 2026-10-14 to 10-15; owner sign-off of P5–P7 still pending |
| P8 (public data) | 4–8 weeks after data | 2026-10-15 to 10-22 (training on Colab, slowed by free GPU limits); TRIAL only |
| Improvements | — | 2026-10-20 to 10-28: UI pass, AI-check banner, platform admin and organization sign-up, place search, roads |
| P9 | 2 weeks | Not started (about 6–8 working days of build work plus owner testing, estimate 2026-10-26) |
| P10 | 1–2 weeks | Demo online (Vercel + laptop tunnel); real hosting depends on PI-18 |
| P11 | 1 week | Word technical document and user manual delivered 2026-10-28 (first handover document) |
| Forecasting track (V2, draft) | — | 6–8 weeks for data and proof of concept, 2–3 weeks to add to the app; suburbs and field pilot depend on the cities and the winter season |
