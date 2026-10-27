# GeoInfraLens AI: Documentation

AI GIS Road and Sidewalk Assessment Platform. Built by one developer, with Claude as senior engineer and mentor.

**Start here every session:** `CURRENT_PHASE.md` says where the project is and what to do next.
All paths in these documents are written from this `documentation/` folder.

## Folder layout

```
documentation/
├── README.md                  this index
├── CURRENT_PHASE.md           where we are now + working rules (read first)
├── project-decisions.md       dated log of every decision and change
│
├── 01-overview/               what the product is and what it's built with
├── 02-process/                how the project is run: phases, checkpoints, build order, timeline
├── 03-requirements/           P1: what version 1 must do, who may do what, customer inputs, tests
├── 04-design/                 P2: database, API, AI output format, screens
├── 05-standards/              rules for writing code
├── 06-demo/                  demo guide and testing guides
├── 07-ml/                    P8: dataset and model cards, evaluation reports
└── source-documents/          the original PDFs (requirements spec, stack proposal)
```

## Files

### Top level
| File | What it answers | Status |
|------|-----------------|--------|
| `CURRENT_PHASE.md` | Where are we, what may the agent do, what are the working rules? | Live |
| `project-decisions.md` | What was decided, when, and why? | Live |

### 01-overview
| File | What it answers | Status |
|------|-----------------|--------|
| `01-overview/project-flow.md` | How does the product work, end to end? | Approved |
| `01-overview/tech-stack.md` | Which technologies, and why? | Approved |

### 02-process
| File | What it answers | Status |
|------|-----------------|--------|
| `02-process/development-model.md` | How is the project run (phased waterfall with gates)? | Approved |
| `02-process/project-phases.md` | What are the phases P0–P11? | Approved |
| `02-process/checkpoints-and-goals.md` | What must be true to finish each phase? | Live checklist |
| `02-process/build-order.md` | In what exact order is the code written? | Live checklist |
| `02-process/timeline.md` | How long will it take? | Estimate, updated per phase |

### 03-requirements (P1)
| File | What it answers | Status |
|------|-----------------|--------|
| `03-requirements/requirements.md` | What must version 1 do (FR/NFR), and what not? | Approved (incl. CR-001) |
| `03-requirements/permission-matrix.md` | Who may do what? | Approved (incl. CR-001) |
| `03-requirements/partner-inputs.md` | What must the customer decide? Placeholders until then | Waiting for customer |
| `03-requirements/acceptance-checklist.md` | The tests the app must pass (AC-01…AC-52) | Live checklist |

### 04-design (P2)
| File | What it answers | Status |
|------|-----------------|--------|
| `04-design/database-schema.md` | Which tables, columns, and rules? | Approved, frozen |
| `04-design/api-spec.md` | Which requests can the screens send? | Approved, frozen |
| `04-design/model-output-contract.md` | What must the AI hand back? | Approved, frozen |
| `04-design/ui-screens.md` | Which screens, and their loading/empty/error states? | Approved, frozen |
| `04-design/ml-baseline-plan.md` | P8: model classes, how it is measured, pass marks, gate | P8.0 approved 2026-10-16 (pass marks PLACEHOLDER) |

### 07-ml (P8)
| File | What it answers | Status |
|------|-----------------|--------|
| `07-ml/dataset-card-rdd2022.md` | Where the training data comes from, its licence, what is inside, known gaps | Draft; counts after the Colab run |

### 05-standards
| File | What it answers | Status |
|------|-----------------|--------|
| `05-standards/coding-conventions.md` | Naming, error format, error handling, quality checks | Approved |

### source-documents
| File | What it is |
|------|------------|
| `source-documents/AI_GIS_Road_and_Sidewalk_Platform_Project_Requirements_and_UI_UX.pdf` | Original product requirements and UI/UX specification |
| `source-documents/AI_GIS_Final_Technology_Stack_With_Reasons.pdf` | Original stack proposal (revised in `01-overview/tech-stack.md`) |

## Rules for keeping documentation organized

- New documents go in the folder for their phase or topic. Phase documents written later go in new numbered folders (for example `06-testing/`, `07-deployment/`, `08-handover/`).
- File names are `kebab-case.md` (see `05-standards/coding-conventions.md`).
- When a decision changes, update the relevant file and add a line to `project-decisions.md`.
- When a phase gate passes, update `CURRENT_PHASE.md` and tick the checkpoint in `02-process/checkpoints-and-goals.md`.
- Customer decisions that are not confirmed are marked **PLACEHOLDER**. Never present them as confirmed.
- If these documents and the source PDFs disagree, record it in `project-decisions.md` and ask the owner. Never pick one silently.

## 06-demo

- `06-demo/demo-guide.html`: plain-language demo guide for the team lead (status, demo script, every screen and option, technology, one-time links, maps, API/Swagger, frontend–backend flow, console messages). Open it in a browser.
