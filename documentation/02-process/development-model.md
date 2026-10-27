# 03: Development Model

## Chosen model: phased waterfall with gates

We follow the **waterfall** idea of phases: requirements, then design, then build, then test, then deploy, then handover. Each phase finishes with a written sign-off before the next starts. We add two adjustments so problems are found early instead of at the end.

## Why waterfall suits this project

- **Fixed, written requirements.** The specification already defines the users, screens, rules, and acceptance criteria.
- **One developer.** Clear phases tell you exactly what to work on and what to ignore.
- **Documentation is a deliverable.** The handover package (requirements, design, API spec, QA results, guides) matches waterfall's document-at-each-phase style.
- **Clear gates.** Each phase ends with checkable criteria, so "done" is never vague.

## Risks of *pure* waterfall here

| Risk | Why it matters for this project |
|------|--------------------------------|
| Testing only at the end | Bugs in authentication or the data model, found after all features are built, are very expensive to fix. |
| Partner inputs are unknown | The severity rubric, priority weights, retention rules, and dataset may arrive late. Pure waterfall would block the build. |
| The AI model is uncertain | Model quality depends on data we don't have yet. The platform must not wait for it. |

## Our adjustments

1. **The design is reviewed and then frozen.** The database schema, API, and permission matrix are designed and reviewed before code. Changes after the freeze go through change control (below).
2. **The build phase delivers in four tested slices**, in strict order:
   - Slice 1: upload
   - Slice 2: analysis
   - Slice 3: review
   - Slice 4: reports

   Each slice is built, tested, and signed off before the next starts. This is still sequential, but every piece is tested while it's fresh.
3. **The ML track runs in parallel.** Dataset, labeling, training, and evaluation proceed when data is available. The platform uses a stand-in detector until the model passes its evaluation gate.
4. **Placeholders are allowed for partner inputs.** The build can continue with clearly marked PLACEHOLDER configuration. Replacing a placeholder is a configuration change, not a redesign.

## Phase gate rules

- A phase is complete only when every item in its checkpoint list (`02-process/checkpoints-and-goals.md`) is ticked.
- The **project owner** signs off each gate. The agent never advances the phase on its own.
- Tests must actually have been run, with results observed, before a gate can pass.
- Known limitations are written down. They are never hidden.

## Change control

Going back to an earlier phase is allowed but recorded. For any change to frozen requirements or design:

1. Describe the change and the reason.
2. List what it affects: tables, APIs, screens, tests, documents.
3. The owner approves or rejects it.
4. Update the documents and add a line to `project-decisions.md`.
5. Write a migration if the schema changes. Never edit an applied migration.

Change record template:

```
Date:
Change:
Reason:
Affects:
Decision: approved / rejected
Follow-up:
```
