Purpose

This file defines expectations for AI coding agents, contributors, and maintainers working within this repository.
Its goal is to ensure that requested changes are surgical, intentional, and non-destructive, maintaining both functional integrity and documentation consistency throughout the codebase.

This repository serves as a FastAPI-based application providing time tracking, client management, and operational tooling for managed IT services. Stability and continuity take precedence over speed of change.

⸻

1. Guiding Principles

Surgical Precision
	•	Modify only what’s necessary. Any change must target a single, well-defined scope (e.g. fixing one bug, refactoring one module, adding one feature).
	•	Avoid sweeping or speculative changes unless explicitly requested.
	•	Each edit should be reversible and traceable.

Integration Awareness
	•	Before submitting a PR or automated edit, analyze dependencies:
	•	Identify other modules that rely on the changed component.
	•	Review function imports, shared schemas, and service calls.
	•	If a change alters expected behavior, update or test all dependents accordingly.
	•	Never assume isolation — FastAPI routers, database models, and schemas are interconnected.

Documentation Discipline
	•	Any code modification that changes functionality, parameters, or API routes must be reflected in:
	•	README.md (user-facing updates, setup instructions, API usage)
	•	Internal docstrings or comments (developer-facing context)
	•	.env.example or configuration guides if environment variables change

Agents and contributors must not leave functional or behavioral changes undocumented.

⸻

2. PR and Commit Standards

Commit Messages
	•	Use concise, descriptive commit messages (e.g. fix: adjust /clients pagination limit, not updated stuff).
	•	Prefix commits with relevant context:
	•	fix: for bug fixes
	•	feat: for new functionality
	•	refactor: for structural improvement
	•	docs: for documentation updates
	•	test: for testing improvements

Pull Requests
	•	One purpose per PR.
	•	Include:
	•	A short summary of what changed and why.
	•	A list of affected files or modules.
	•	A note of any related documentation updated.
	•	A confirmation that the application was run/tested successfully (uvicorn start OK, endpoints respond, etc.).

⸻

3. Change Evaluation Checklist

Before committing or merging, agents and maintainers should evaluate:
	1.	Scope clarity:
Is the change isolated to its intended purpose?
	2.	Dependency awareness:
Have all relevant imports, models, and routers been checked for impact?
	3.	Documentation parity:
Is the README.md or related doc updated accordingly?
	4.	Integration tests:
Does the app build and start without regression?
(For example, no schema mismatches, unresolved imports, or template errors.)
	5.	Style consistency:
Does the change maintain project conventions (formatting, naming, REST patterns)?

⸻

4. Special Considerations for AI Agents

If this repository is being used with code generation tools such as GitHub Copilot, ChatGPT, or internal automation systems:
	•	Minimize collateral edits.
AI agents must avoid “cleanup passes” that reformat or rename unrelated parts of the code.
	•	Always cross-reference changes with the README.
If a modification makes an example or endpoint obsolete, the README must be updated in the same PR.
	•	Run dependency diff checks.
Agents should verify imports and references to detect broken links before pushing.

⸻

5. Integration Reevaluation Process

When modifying a key component (models, routers, services, or templates):
	•	Inspect all other layers that consume it:
	•	Models → CRUD → API routers → Templates
	•	Identify whether the integration requires adjustment or docstring clarification.
	•	If behavior was changed intentionally, note it under a “Behavioral Changes” heading in the PR description.

The objective is tight coupling awareness without over-engineering — firm up integration only where it improves reliability.

⸻

6. Style and Consistency Rules
	•	Follow PEP 8 for Python formatting.
	•	Use snake_case for variables and functions, PascalCase for classes.
	•	Keep configuration paths, templates, and API routes lowercase and consistent.
	•	Maintain a single source of truth for environment variables (in .env.example).
	•	FastAPI path naming convention: /resource/action or /resource/{id}.
	•	Ensure HTML templates maintain styling parity (don’t break layout or CSS alignment).

⸻

7. Post-Change Validation

After every merged change:
	•	Run docker-compose up --build or equivalent local test to confirm build success.
	•	Access the web UI and validate page renderings.
	•	Re-check API endpoints (manual curl or FastAPI docs UI).
	•	Confirm database migrations or schema files remain valid.

⸻

8. Example Agent Workflow
	1.	Receive a user request (e.g., “Add duration tracking to the ticket endpoint”).
	2.	Locate related modules:
	•	/models/ticket.py
	•	/schemas/ticket.py
	•	/routers/tickets.py
	3.	Make only the necessary edits.
	4.	Run the application and confirm no errors.
	5.	Update the README’s API reference.
	6.	Summarize changes and create a single PR labeled feat: ticket duration tracking.

⸻

9. Final Word

This project prioritizes continuity, clarity, and controlled evolution.
Innovation is welcome, but chaos is not.
Change what’s broken, strengthen what’s weak, and document every move.