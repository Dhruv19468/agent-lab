# BRD to Test Plan

Turn a Business Requirements Document (BRD) and an architecture diagram or description into a complete, reviewable test plan. Works for any project: nothing here is specific to one application.

## When to Use

Use this skill when the user asks for a test plan, QA plan or test strategy based on a BRD or similar requirements document.

**Trigger phrases:** test plan, generate test plan, create test plan, draft test plan, brd to test plan, test plan from brd, test strategy from brd, qa plan

## What you can and cannot do

- You read your input documents from the Agent Lab data folder with your tools. The user's message normally names the project folder, for example `raw/validation/P06_Rebate_Validation`.
- Each message is handled on its own. You do not remember earlier messages, so never refer to what you said before and never rely on a later reply such as "continue". Everything you need must be in the current message and the data folder. This means the whole plan must be written in this one message.
- Your final reply is the complete test plan in Markdown. Agent Lab stores it, scores it and turns it into Word, Excel or PDF when the user downloads it. Never reply with only a summary or a link.
- You can look at images. An architecture diagram saved as a PNG or JPG is readable with `view_image`: read every box, zone, arrow and arrow label in it.
- You cannot see reference test plans or answer keys. They are hidden on purpose; do not look for them.

## Working with files in the data folder

You have four tools. Use them to get your input and, when asked, to save a file; never guess what a file contains.

| Tool | Purpose | Use it when | You send | You get back |
|---|---|---|---|---|
| `list_files` | Lists the folders and files in one folder | You need to find the project folder or its documents | `folder`: a path such as `raw/validation/P06_Rebate_Validation`, or `""` for the top | Names, types, paths and sizes. Never the contents |
| `read_file` | Reads one file as text (Word .docx, Markdown, text, JSON, CSV). Word comes back as Markdown with headings and tables | You have found an input document | `path`; `offset` to continue a long file | `text`, `next_offset`, `total_chars`. While `next_offset` is not null, call again with that `offset` until you have read it all |
| `view_image` | Shows you an image (PNG, JPG) | The project has an architecture diagram | `path` | The image, in the next message |
| `create_document` | Saves a document in `agent-output/`. You write Markdown; the file extension picks the format: `.md`, `.docx`, `.xlsx` or `.pdf` | The user asks for a file or a format | `path` (a file name such as `P06_Test_Plan.docx`) and `content` (the complete Markdown) | `path`, `format` and `saved: true` |

Finding your input files:

1. If the message names a folder or a file, use it. Call `list_files` on the project folder first.
2. Otherwise call `list_files("")` and go down `raw/` and its split folders (`train`, `validation`, `test`) until you find the folder whose name starts with the project ID or contains the project name from the message.
3. In the project folder: the BRD is the `.docx` with `BRD` in its name; the architecture is the `.png` or `.jpg` (usually with `Architecture` in its name), or a text file describing the architecture. A QA Standards document, when one exists, has `QA_Standards` or `Standards` in its name, in the project folder or a top-level `standards/` folder.
4. If no BRD is there, say which folders you looked in and stop. Do not write from general knowledge.
5. When you need several files, ask for all of them in the same step, so they are read at the same time.

Reading your input files:

- Read every input document in full. With `read_file`, keep calling with `next_offset` until it is null. Never start writing after reading only part of a document.
- Look at every architecture image with `view_image` before writing.

Saving a file (only when the user asks for a file or a format):

- After writing the plan, call `create_document` once with the complete plan and a name such as `<ProjectID>_Test_Plan.docx` (or `.xlsx`, `.pdf`, `.md` as asked). Then still reply with the complete plan.
- If the tool says the file already exists, call it again with `_v2` added to the name, then `_v3`, and so on.
- Never claim a file was saved unless the tool returned `saved: true`, and give the path exactly as the tool returned it.
- If saving fails and you cannot fix it, reply with the complete plan anyway and say that saving failed and why.

## Inputs

| Input | Required | If missing |
|---|---|---|
| BRD (or equivalent requirements document) | Yes | Say what you looked for and stop. Do not write a plan from general knowledge. |
| Architecture: a diagram image (PNG/JPG) or a text description (Zones, Components, Connections, Data Flows, Security and Data Stores) | Yes | Stop and ask for it. See "Check the inputs first". |
| QA Standards document: the QA team's own tools, environments, entry and exit thresholds, defect severities, test data policy, AI evaluation approach, standard roles, and any project-specific team size or schedule | No, but strongly recommended | Use the defaults in this skill, mark each as an ASSUMPTION, and list "QA Standards document not provided" in the hand-off notes. |
| Project facts: name, version, date, author, reviewers, approver, product owner, named testers | No | Use what the documents state. Anything else is a TBD. Never invent names. |
| Review comments or an earlier plan | No | See "Revising an existing plan". |

Source rule: every fact in the plan comes from the BRD, the architecture, the QA Standards document, the user's message or review comments. When a fact comes from the QA Standards document, write "(QA Standards)" after it the first time it appears. When a fact comes only from the architecture diagram, write "(architecture diagram)" after it the first time it appears.

## Check the inputs first

Before you do anything else, find your input documents (see "Working with files in the data folder") and confirm what you have.

1. **No BRD found:** say which folders you searched, and stop.
2. **BRD found but no architecture (no diagram image and no description):** do not write the plan. Reply with a short message that says the architecture is needed, explains that the architecture-driven tests, interface tests and security tests in the plan depend on it, tells the user to add the diagram or a description to the project folder, and says that if they really want the plan without it they must send the request again with the words "proceed without architecture" in the same message, for example: "Create the master test plan for project P06, proceed without architecture." Then stop.
3. **Architecture image that shows no readable components** (blank, too blurred, or not an architecture): treat it as missing and follow step 2.
4. **Both found:** carry on. If the architecture leaves much unclear, carry on and list the gaps.
5. **The current message explicitly says to proceed without the architecture (for example "proceed without architecture"):** carry on. In section 6 write `[TBD: architecture description or component list. Owner: Solution Architect]`, base the architecture-related tests on what the BRD says, and put "Plan written without an architecture description" as the first item in section 21 and in the hand-off notes.

Never decide on your own to proceed without the architecture. Only an explicit instruction in the current message allows it.

## Step 1: Read the documents properly

Read each input document in full (see "Reading your input files"). Make sure you have seen every section of the BRD, not only the 14 topics below. Then make sure you have the facts for each topic below and keep them.

1. Project name, purpose, business problem, stakeholders
2. Goals and objectives, expected benefits
3. In scope, out of scope, phases or releases (MVP, release, wave)
4. Personas, roles, access rules
5. Functional requirements, use cases, user stories, epics, acceptance criteria
6. Non-functional requirements: availability, performance, security, privacy, compliance, observability, data volumes
7. Integrations, interfaces, data sources, file formats
8. Business rules: calculations, weights, thresholds, score ranges, status rules, formulas
9. Data: sources, quality rules, retention, refresh or scheduling, failure handling
10. Architecture, hosting, environments, tools named in the documents. In the architecture diagram, note every zone, component (box), connection (arrow) with its label (protocol, port, authentication such as OAuth 2.0 or Managed Identity), data store, external system and supporting service.
11. Assumptions, constraints, dependencies, approvals
12. Dates, milestones, launch targets
13. Risks and mitigations
14. From the QA Standards document, if provided: tools, environments, thresholds, severities, data policy, AI evaluation approach, roles, team size, schedule

### Build the BRD inventory

Before extracting requirements, build a checklist of everything the BRD asks for. You will use it in the final check.

- Every item in the BRD's in-scope list, with its status as the BRD writes it (for example "Requirements defined" or "<group> Pending").
- Every requirement label the BRD uses (for example BR-1 to BR-9, FR-1, US-12), whatever its formatting. Labels are often not formatted as headings, and numbered lists ("1. MVP1: …") count as requirements too. Search the text for the label pattern itself, such as "BR-", so none is missed.
- Every business rule table (thresholds, Red/Amber/Green rules, weights, formulas).
- Every role or access table.

### When something cannot be found

- If you cannot find a topic after reading the whole document, write `[TBD: not found in BRD for <topic>. Owner: Business Analyst]` and list it in section 21.
- Never write that the BRD lists something as TBD, pending or undefined unless you quote the BRD text that says so, with its section. "I could not find it" and "the BRD says TBD" are different statements.
- If the BRD's scope list says an item is defined ("Requirements defined") but you cannot find its detail, do not call it TBD. Search again for its label and its name. If you still cannot find it, write `[TBD: detail for <item> not found although the BRD scope lists it as defined. Owner: Business Analyst]`.

## Step 2: Extract the requirements

Build a numbered list of testable requirements.

- Reuse the BRD's own IDs when it has them. Otherwise number them BR-001, BR-002 and so on, in document order.
- One requirement per row, in one sentence of no more than 25 words. Split a requirement that contains several separate testable statements.
- Keep measurable targets exactly as written, including the number and unit (a percentage, a time limit, a volume or a refresh interval stays exactly as the BRD writes it).
- Record the BRD section each requirement came from.
- Priority: use the BRD's own priority or phase if it gives one. Otherwise assign High, Medium or Low from business impact and write `[ASSUMPTION: priority assigned by QA]` once, in the table note.
- Include non-functional, security, compliance, data and reporting requirements, not only features.
- Separate the "do" from the "extract". When a requirement asks the system to act on data (flag, alert, notify, block, restrict), that action is its own requirement, separate from the extraction. Example: "<act on a value>" is a separate row from "<extract that value>".
- Large extraction tables (a list of fields to extract): one row per table, naming the table and the number of fields, for example "Extract the N fields listed in the <name> table". Each field is then covered through the labelled test data in section 10, not as its own row.
- Access rules: one row per role and action the BRD states, for example "<role> sees only the records assigned to them".

### Extract business rules at rule level

Every business rule table or threshold list in the BRD goes into section 4.2 as its own table, one row per rule. Copy each condition exactly as the BRD writes it. Do not summarise a rule as "based on the rules defined in the BRD".

| Column | What it holds |
|---|---|
| Rule ID | BR-x.R1, BR-x.R2 and so on |
| Subject | What the rule applies to, as the BRD names it |
| Condition per outcome | Each outcome and its condition, quoted from the BRD (for example Green: "<condition>"; Amber: "<condition>"; Red: "<condition>") |
| Boundary values to test | The values just below, on and just above each threshold the BRD gives |
| BRD section | Where the rule is |

If a rule has no number (a rule written only in words), quote it and test it with labelled examples instead of boundary values. If the conditions overlap, leave gaps between them or contradict each other, list that in section 21.

## Step 3: Find problems in the BRD

Before writing the plan, check the BRD for problems a tester must raise. List each one in section 21 with the BRD section reference and who should resolve it.

- Contradictions: the same value stated two different ways (for example two different weightings for the same score).
- Scope conflicts: something listed both in scope and out of scope, or in the wrong phase. Check every out-of-scope item against the feature descriptions (for example "Recommendation" out of scope while a dashboard shows "suggested actions").
- Missing or empty parts: sections marked TBD or left blank, "open question" notes, links to documents that were not provided.
- Vague wording with no measure: "quickly", "near real time", "acceptable", "high accuracy", "as appropriate".
- Dates that are already in the past or inconsistent with each other.
- Requirements with no acceptance criteria.
- Status notes that affect testing (for example "<group> Pending" means that data is not yet available as test data).
- Spelling or label differences that could mean two different things.
- Formatting that makes the document hard to read reliably (for example requirement labels that are not formatted as headings).
- Differences between the BRD and the architecture diagram (a component in one but not the other).

Do not silently pick one side of a contradiction. Test against what the BRD says in its main requirement text, say which source you used, and list the conflict.

## Step 4: Write the plan

Use exactly these 22 sections, in this order, with these headings. Do not add, remove, merge, rename or repeat sections. This covers what a reference test plan contains: Introduction and Objectives in 2, Scope in 3, Technology and QA focus in 6, Test Types and Priority in 5, AI Evaluation Strategy and its implementation in 8, Failure Injection and Performance in 6 and 7, Test Environment in 9, Test Data in 10, Entry and Exit Criteria in 11, Schedule in 13, Detailed Efforts and Sequence in 14, Resources in 15, Risks and Mitigation in 16, Tools and Automation Strategy in 17, Deliverables in 18, Success Criteria in 19.

1. Document Control
2. Introduction and Objectives
3. Scope
4. Test Items and Features
5. Test Approach
6. Architecture-driven Test Considerations
7. Non-Functional Testing
8. AI Evaluation Strategy
9. Test Environment
10. Test Data Strategy
11. Entry, Exit and Suspension Criteria
12. Defect Management
13. Schedule and Milestones
14. Execution Sequence and Effort
15. Roles and Responsibilities
16. Risks and Mitigations
17. Tools
18. Test Deliverables
19. Success Criteria
20. Test Scenarios and Requirements Traceability
21. Assumptions, BRD Observations and Open Items
22. Approvals

### Section guidance

**1. Document Control.** Table: Identifier (TP-<short project code>-v1), Status (Draft, for review), Author, Reviewers, Approver. Add a revision history table: version, date, change, source. Use names only if the user or documents gave them.

**2. Introduction and Objectives.** Header facts: Project Name, Version, Prepared By, Date. Then one short paragraph on the business objective and why testing is needed, in the project's own words. Then the testing objectives as a bulleted list (for example validate end-to-end workflows, role-based access, scoring, data pipelines, reliability). Name the main risk to the business if the system fails.

**3. Scope.** In scope and out of scope as bullet lists taken from the BRD, under the sub-headings `### In scope` and `### Out of scope`. Every item in the BRD's in-scope list appears here, with the requirement IDs that cover it and its status as the BRD writes it. Label items by phase or release when the BRD does. Add a two-column table of business workflows or features in scope. State that anything not listed is out of scope unless added through change control.

**4. Test Items and Features.** 4.1 Requirements: table of the extracted requirements with columns ID, requirement (one sentence), BRD section, priority, phase. 4.2 Business Rules: the rule table from Step 2, or one line "No business rule tables in the BRD".

**5. Test Approach.** Overall approach, then these sub-headings: Testing Types and Priority (a table: test type, priority P0, P1 or P2, why; include functional, API, AI testing, integration and end-to-end, data validation, security, performance, UI, failure injection, regression, as the project needs), Testing Levels (unit, component, system, user acceptance), Test Design Approach, Automated API Testing, Automated UI Testing, Manual Testing, Phase focus, Traceability. Choose what applies to this project from the BRD. If the system has no UI, say UI automation is not applicable. If it has no API, say so. Test-type priorities come from the QA Standards document when it gives them; otherwise assign them and mark `[ASSUMPTION: test-type priority assigned by QA]`.

Test design techniques to apply where relevant, and name them in the plan: equivalence partitioning, boundary values, decision tables, state transitions (only for states the BRD defines), error guessing, data-driven tests, and negative and edge cases.

Apply these when the BRD contains the matching feature:
- Calculations, scores, weights or status bands: recompute the result independently from the inputs, test every boundary in section 4.2 (just below, on, just above), and test weights that must add up to 100%.
- AI or machine-learning behaviour: see section 8.
- Data ingestion and scheduled refresh: test each source, file formats and structure, duplicates, missing and corrupt records, failed source handling, the refresh timestamp, and re-upload or archive rules.
- Temporary or non-persisted data (for example an upload "not stored in the database"): test that nothing is written to any data store, cache, index or log beyond what the BRD allows.
- Dashboards and reports: reconcile every displayed figure back to its source data, and test filters, sorting, drill-downs and last-refresh display.
- Roles and access: build a role-by-action matrix only from the BRD's role and access tables, and test allowed and denied cases for each role, including data scoping (a user sees only what is assigned to them). Every role statement in the plan cites its BRD section. Never give a role an ability the BRD does not give it, and never name a role the BRD does not have.
- Identity: sign-in, sign-out, session expiry, role mapping.
- Integrations: contract tests, timeouts, retries, and behaviour when the other system is down.
- Audit and traceability: every result traces to its source, batch and rule version, and changes to rules are logged.
- Privacy: personal data minimised. Use masked or synthetic data in non-production unless the QA Standards document or the BRD states another agreed policy; then follow that policy and cite it.

**6. Architecture-driven Test Considerations.** Use the architecture directly. From a diagram: each box is a test item, each arrow is an interface test (its label gives the protocol and authentication), each path of arrows from user to data store is an end-to-end scenario, and anything the diagram leaves unclear becomes a BRD observation. From a text description: use its Components, Connections, Data Flows and Known Gaps tables the same way. Sub-headings:
- 6.1 Components and QA focus: a table of component, technology as the architecture names it, QA focus (what testing must prove for it). Use the exact component names from the architecture.
- 6.2 Interfaces: each connection with protocol, authentication and failure behaviour.
- 6.3 End-to-end flows: one scenario per data flow, written as the chain of components (for example <user> → <gateway> → <service> → <queue> → <processing> → <AI service> → <database> → <UI>), using the architecture's own names.
- 6.4 Failure and resilience scenarios: for each external dependency and each step of the main data flow, one failure scenario and its expected handling (for example storage failure → retry and error message; model timeout → retry or fallback; low-confidence retrieval → flagged, not guessed; API error 500 → graceful message; missing clause → no invented answer).
- 6.5 Known architecture gaps: carry the unclear items into section 21 instead of guessing.
Add data management, workflow and orchestration, integration contracts, logging and monitoring, scalability, and environment configuration considerations where the BRD or the architecture supports them. Only when the message explicitly said to proceed without an architecture, write one line stating that and add `[TBD: architecture description or component list. Owner: Solution Architect]`.

**7. Non-Functional Testing.** One sub-heading per NFR in the BRD (availability, performance, security and privacy, observability, compliance, accuracy, accessibility and usability). Name each sub-heading after its NFR, for example `### Availability`, `### Performance`, `### Security and privacy`, `### Accessibility and usability`. Quote the target. If the target has no number, write `[TBD: measurable target. Owner: Product Owner]`. For performance, name what will be measured (for example document processing latency, model response time, batch ingestion throughput, API concurrency) even when the target is a TBD, and say that the first test cycle sets the baseline.

**8. AI Evaluation Strategy.** Write this section when the BRD has any AI behaviour (extraction, classification, scoring by a model, summaries, recommendations, chat or search answers). Otherwise write one line: "Not applicable: the BRD describes no AI behaviour." Sub-headings:
- 8.1 Golden dataset: a labelled set of real or representative inputs with the expected outputs (extracted fields, scores, answers), labelled by QA and signed off by the Product Owner or subject matter experts. Include edge cases: missing, conflicting and ambiguous content, and poor-quality inputs such as scans.
- 8.2 AI metrics by priority: a table of metric, priority, target, how measured. P0 (needed to go live): accuracy against the golden dataset for each AI output, groundedness (answers supported by the source), rule compliance, retrieval accuracy, consistency across repeated runs. P1: reasoning quality, faithfulness, precision and recall of flagged issues. P2: robustness to input variation, latency, token cost. Targets come from the BRD or the QA Standards document; otherwise `[TBD: target for <metric>. Owner: Product Owner]`.
- 8.3 Evaluation method: batch runs of the golden dataset through the system, comparison of actual with expected output, human review of a sample. Name evaluation tools only when the documents name them; otherwise `[ASSUMPTION: evaluation tool to be chosen by QA]`.
- 8.4 Non-deterministic output: AI output can vary between runs, so pass and fail use thresholds over repeated runs, not single exact matches.
- 8.5 Hallucination and grounding checks: missing content must produce "not found", not an invented value; conflicting content must be flagged; every answer must point to its source.
- 8.6 Regression on change: re-run the golden dataset after every model, prompt, rule or pipeline change.

**9. Test Environment.** Environments, which release content is deployed to each, configuration, connectivity, tools and pipelines, security and access (who needs read-only or write access to which databases, monitoring tools and AI services), readiness checklist. Use only environment names and tools found in the documents, the architecture or the QA Standards document. Everything else is a TBD with an owner role.

**10. Test Data Strategy.** Principles, a table of data sets (data set, description, source, requirements covered), the golden dataset from section 8, data preparation including edge, error and boundary data (use the boundary values from section 4.2), privacy and masking (see the privacy rule in section 5), test data traceability. Say which data is not yet available when the BRD gives a status such as "pending".

**11. Entry, Exit and Suspension Criteria.** Entry, exit, suspension and resumption criteria. Use thresholds from the BRD first, then the QA Standards document. When neither has them, use these defaults and mark each as `[ASSUMPTION: standard QA threshold]`:
- Entry: unit testing completed by development with at least 85% code coverage; smoke test passed at 100%; no open High or Critical severity defects; API contracts shared with QA; test environment deployed and stable; QA access to databases, tools and AI services confirmed; no High vulnerabilities in the code scan.
- Exit: all planned test cases executed with at least 95% passed; all Critical, High and Medium severity defects closed or deferred with stakeholder approval; regression suite passed with no critical failures; every measurable BRD and AI metric target from sections 7 and 8 met; test reports shared.
Exit criteria must include every measurable acceptance target from the BRD.

**12. Defect Management.** Lifecycle, required defect fields, severity levels (Critical, High, Medium, Low) with examples from this project, triage and assignment, retest and regression, metrics, production defects. Use the QA Standards severities if they differ. The defect tool is a TBD unless the documents name one.

**13. Schedule and Milestones.** Use only dates and durations the documents give. A launch date from the BRD is a milestone, not a test schedule. If the QA Standards document gives a phase plan (for example Phase 1 functional, Phase 2 AI and pipeline, Phase 3 performance), use it. If there are no test dates, write one line: `[TBD: test schedule. Owner: Project Manager]`. If a BRD date is already in the past, say so here and list it in section 21.

**14. Execution Sequence and Effort.** A table: sequence, activity, primary owner role, dependencies, expected outcome. Order: requirement walkthrough, environment readiness, golden dataset preparation (if section 8 applies), functional test design, API and integration test design, functional execution, AI evaluation, end-to-end validation, automation and regression suite, failure and resilience testing, performance testing, regression and sign-off. Then list the extra effort AI testing needs beyond standard QA (golden dataset labelling, custom evaluators, repeated runs, domain ramp-up, subject matter expert reviews) when section 8 applies. Effort figures only from the documents; otherwise `[TBD: effort estimate. Owner: QA Lead]`.

**15. Roles and Responsibilities.** Table: role, name, responsibilities. Include plan author, product owner, QA lead, functional QA, automation QA, AI QA (when section 8 applies), business testers for acceptance, environment owner, developers, security and compliance, and data owner. Names and team sizes come only from the user, the documents or the QA Standards document.

**16. Risks and Mitigations.** Table: ID, risk, likelihood, impact, mitigation. Start with the risks the BRD itself lists, then add risks based on this BRD and architecture: requirement changes, data quality and availability, integration dependencies, access to environments and tools, system downtime, AI accuracy, AI usage or token limits, QA domain knowledge, approvals, scope, availability of business testers, performance, privacy. Mitigations must be concrete and testable.

**17. Tools.** Group by purpose (test management, defect tracking, UI and API automation, AI evaluation, performance, security, data validation, monitoring, reporting, pipeline). Use named tools from the documents, the architecture or the QA Standards document. Otherwise write the category once with `[ASSUMPTION: tool to be chosen by QA and DevOps]`. Say what each automation tool covers (UI, API, AI checks).

**18. Test Deliverables.** List the deliverables (test cases, automation scripts, AI evaluation reports, test reports, defect reports, sign-off pack) and a short phase table. Each deliverable once.

**19. Success Criteria.** A short list of what "testing succeeded" means for this project: each measurable target from the BRD, the P0 AI metric targets from section 8, and correct behaviour of the main business rules. Targets with no number stay as the TBDs already listed in sections 7 and 8.

**20. Test Scenarios and Requirements Traceability.** First a scenario table: ID (TS-001, TS-002 and so on), scenario title, requirement IDs, level, type, priority, expected outcome in one line. Write one to three scenarios per requirement, and for every High requirement include at least one negative or edge scenario. Every business rule in section 4.2 has at least one boundary scenario. Include one end-to-end scenario per main business flow, written as numbered steps from sign-in to the final outcome. Then a traceability matrix: requirement ID, requirement, scenario IDs, level, priority. Every scenario ID in the matrix must exist in the scenario table, and every requirement must have at least one scenario. Do not use ranges of IDs that have no scenarios behind them.

**21. Assumptions, BRD Observations and Open Items.** Three sub-headings. Assumptions: every ASSUMPTION used in the plan, once each. BRD Observations: the problems found in Step 3, as a table (observation, BRD section, why it matters, who resolves it). Open Items: every TBD in the plan, once each, with the section number.

**22. Approvals.** Table: role, name, decision, date. Use the approvers the BRD lists. Decision is "Pending" for everyone and date is "-" unless the user gave different information.

## Writing rules

- Plain, direct business English. Short sentences. No marketing language.
- Use the project's own terms exactly as written in the documents.
- Prefer tables for more than three comparable items. Keep table cells short.
- Never pad a section. When the documents say nothing, write one TBD line.
- A missing fact is `[TBD: what is missing. Owner: role]`.
- A default you chose on purpose is `[ASSUMPTION: what you assumed]`.
- Do not invent names, dates, tool names, environment names, numbers, supplier or product details, roles' abilities, system behaviour or approval outcomes.
- Every statement about what the system does, or who can do what, must be traceable to a BRD or architecture section. If it is your own test idea, write it as a test ("test that…"), not as a fact about the system.
- Every requirement ID you cite must exist in section 4.
- Never copy a statement about another project, and never reuse a value from an example in these instructions. Everything must come from this project's documents.

## Output format

- Write Markdown: `##` for the 22 section headings, written as `## 1. Document Control` to `## 22. Approvals`; `###` for sub-headings; `- ` bullets with at most two levels; pipe tables with short cells. No HTML, no code blocks, no emoji, no horizontal rules.
- First line of the plan: `Internal Use Only | Confidential`. Then the title line: `# Test Plan: <project name>` followed by the identifier. Last line of the plan: `Internal Use Only | Confidential`.
- Write the whole plan in this one reply. If the BRD is large, shorten the scenario descriptions to one line each rather than leaving sections out.
- When the user asks for specific sections (for example "generate test plan sections 11 to 22"), write only those sections, but still read the BRD fully and extract requirements in document order, so requirement IDs and scenario IDs come out the same as in a full plan.
- After the last line of the plan, add a short block starting with `Hand-off notes:` (plain text, not a heading):
  - Input files used (paths), and the saved file path if you saved one.
  - BRD inventory coverage: how many in-scope items and requirement labels the BRD has, and confirmation that each maps to section 4, or which do not.
  - Number of requirements and business rules found, number of TBDs and assumptions.
  - The three most important BRD observations.
  - What the user should provide to close the biggest gaps (for example the QA Standards document, missing architecture details, roster, dates).

Formatting note: the downloadable Word, Excel and PDF files are produced from your Markdown by Agent Lab. Do not try to draw a logo or watermark.

## Revising an existing plan

- The message gives the earlier plan's path (for example `agent-output/P06_Test_Plan.md`) or pastes the comments. Read the earlier plan with `read_file` first.
- Apply exactly what each comment asks and keep all other wording unchanged.
- When a comment gives a fact (a date, a target, a name), replace the matching TBD with it and remove it from the open items.
- When a comment points to a document in the data folder, read it and use the facts in it.
- When a comment is unclear, make the smallest sensible change and add an ASSUMPTION.
- Add a row to the revision history for each revision. If asked to save, save under a new name (`_v2`).

## Final consistency check

Before you finish, check and fix. Do not restyle or shorten.

- Completeness: the plan holds all 22 section headings, each once, in order.
- BRD inventory: every in-scope item and every requirement label from the inventory maps to at least one row in section 4.1, and every business rule table appears in section 4.2.
- TBD claims: no sentence says the BRD lists something as TBD, pending or undefined unless it quotes the BRD text. A scope item the BRD calls defined is never called TBD.
- Faithfulness: every role ability and system behaviour stated as fact cites a BRD or architecture section. No role can do something the BRD restricts to another role.
- Scope, schedule, risks, test data, entry and exit criteria, roles and approvals agree with each other. For example, never assume environments are available "on the dates in section 13" when section 13 has no dates.
- Every requirement has a scenario, every scenario exists in the table, every business rule has a boundary scenario, and priorities match between sections 4 and 20.
- Every measurable BRD target appears in exit criteria, non-functional testing, AI evaluation or success criteria.
- Section 21 lists every ASSUMPTION and TBD that appears in the plan, and no others.
- No names, dates or tools appear that the user, the documents or the architecture did not give.
