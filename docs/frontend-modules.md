# Frontend Modules v1

Stage D reduces the maintenance risk of `app/static/app.js` without changing
the workflow, API, persistence, or security contracts established in Stages
A-C. The first extraction is deliberately limited to Creator report rendering
and the settings panel.

## 1. Load order

The home page loads scripts in this explicit order:

1. `workbench.js`: shared Workbench shell helpers and navigation events.
2. `modules/creator-report-view.js`: pure Creator report markup and bounded DOM rendering.
3. `modules/settings-panel.js`: settings modal rendering and UI coordination.
4. `app.js`: the single-work and Creator workflow controller.
5. `workbench-tasks.js`: Stage A/B overview, task observation, and recovery controls.

Modules are regular local scripts. There is no dynamic loader, remote script,
build chain, or timing-based dependency. The server static version includes
all module files.

## 2. Major globals

Only frozen, named namespaces are added:

- `window.WorkbenchShell`
- `window.CreatorReportView`
- `window.SettingsPanel`

`app.js` remains the owner of workflow state, including
`currentCloneSetId`, selection state, active Job identifiers, current Runtime
state, and the six-step Creator stage. Extracted modules do not duplicate or
mutate those values.

## 3. DOM ownership

- `CreatorReportView` owns markup written inside the explicitly supplied
  Creator report container and the report render-failure fallback. It does not
  navigate stages, scroll the page, unlock actions, or modify Job status.
- `SettingsPanel` owns modal open/close behavior, settings status blocks,
  form busy states, test-result messages, and settings form values. It receives
  all DOM elements explicitly during initialization.
- `app.js` owns the home route, single-work result, Creator six-step sections,
  Job card, enrichment/distillation controls, report-stage navigation, and
  Strategy Plan.
- `workbench-tasks.js` owns the Stage A/B task overview root.
- `library.js` owns the `/library` page.

Missing optional DOM causes a safe no-op. Initialization is idempotent so a
script cannot register duplicate listeners.

## 4. API ownership

- `app.js` remains the controller for all single-work, Creator Runtime,
  enrichment, distillation, Strategy Plan, and recovery APIs.
- `SettingsPanel` calls only the existing settings endpoints through the
  injected request function: LLM status/save/test, Douyin data-source
  status/save/test, and preflight refresh. Endpoint paths and payloads are not
  changed.
- `workbench-tasks.js` owns `/api/workbench/overview` and read-only Job
  observation.
- `library.js` owns `/api/library/assets`.
- `CreatorReportView` performs no network request.

## 5. Events and CustomEvent contracts

Existing events remain unchanged:

- `workbench:coming-soon`
- `workbench:navigate`
- `workbench:open-url`
- `workbench:open-target`
- `workbench:target-result`

The extracted modules do not introduce workflow events. `SettingsPanel`
uses direct callbacks supplied by `app.js`; `CreatorReportView` returns a
boolean render result. This avoids duplicate dispatch and preserves Stage B
recovery semantics.

## 6. Creator six-step dependencies

The six-step flow remains entirely in `app.js`:

`import -> pool -> select -> enrich -> distill -> export`

The report module is called only after a result has already been selected by
the Runtime/controller. It cannot create a sample set, select samples, poll a
Job, call an LLM, mark a stage complete, or choose a next action. The controller
still decides when to reveal `export`, when to scroll, and when Strategy Plan is
available.

## 7. Safe extraction boundaries

Safe v1 boundaries are:

- deterministic report normalization and HTML generation;
- safe text escaping and bounded list rendering for that report;
- report container completion checks and render-failure fallback;
- settings modal visibility;
- settings status rendering and form/test busy-state coordination.

Every module receives data and DOM references explicitly and exports a frozen,
minimal API.

## 8. High-risk boundaries not extracted

The following stay in `app.js`:

- Creator Runtime state machine and six-step navigation;
- `currentCloneSetId`, pool, selection, and enrichment state;
- enrichment/distillation polling and timeout decisions;
- Workbench precise recovery and stale handling;
- single-work import/download/build/analyze flow;
- Strategy Plan generation;
- Cookie/API persistence and backend security contracts.

## 9. Dependency direction

Dependency direction is one-way:

```text
workbench.js -> creator-report-view.js / settings-panel.js -> app.js
workbench.js -> app.js -> workbench-tasks.js
library.html -> library.js
```

`app.js` may call exported module APIs. Extracted modules never call functions
defined inside `app.js` by global name; required behavior is provided through
explicit initialization callbacks.

## 10. No-cycle rules

- Modules must not import or dynamically load one another.
- Modules must not read workflow globals from `app.js`.
- `CreatorReportView` must not fetch or dispatch workflow events.
- `SettingsPanel` must not read or write Creator workflow state.
- `app.js` must not copy module-owned render/event implementations back into
  the controller.
- A future extraction must document its owner, inputs, outputs, and forbidden
  dependencies before code is moved.
