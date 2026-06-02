# Explain the Dataverse Flow — Skill README

Turn the hard-to-read cloud flow files inside an exported Dataverse / Power Platform
solution into a clean, **beginner-friendly Markdown report**.

Exported solutions store each Power Automate cloud flow as a large machine-format JSON file
under a `Workflows/` folder. This skill reads those files (read-only — it never modifies the
solution) and explains, in plain English, what each flow does.

---

## When to use it

Use this skill when you have:

- a **solution `.zip`** exported from Dataverse / Power Platform, **or**
- an **unpacked solution folder** (one that contains a `Workflows/` directory),

…and you want to **understand, document, review, or summarize** the cloud flows inside it.

Typical prompts that trigger it:

> "What do these flows do?" · "Summarize my solution's flows" ·
> "Explain this exported solution" · "Make these exported flows readable"

---

## What you get

A Markdown report containing:

- **Solution summary** — how many cloud flows, which connectors are used across them
  (with usage counts), and the biggest flows by step count.
- **Flows by type** — counts of Automated / Instant / Scheduled / Other.
- **Contents table** — every flow grouped by type, with its trigger, connectors, and step
  count, linking to the per-flow detail.
- **Per-flow details**:
  - **At a glance** — a one-line plain-English summary.
  - **Starts when** — the trigger (event, schedule, button, Power App, agent, etc.).
  - **Role** — Parent / Child / Standalone.
  - **What it does in connected systems** — operations grouped by friendly connector name.
  - **Dataverse tables touched**.
  - **Child flows it calls** — de-duplicated, with counts.
  - **Logic used** — a concise summary of connector actions, decisions, and data-prep steps.

The report avoids raw internal identifiers (e.g. `OpenApiConnection`,
`shared_commondataserviceforapps`) in the main view. Use `--technical` if you want those too.

---

## Requirements

- **Python 3** available on your PATH (no third-party packages required — standard library only).

---

## How to use it

### Option A — Just ask Copilot

Point Copilot at your solution and ask it to explain the flows, for example:

> Explain the cloud flows in `C:\path\to\MySolution_managed.zip`

Copilot loads this skill, runs the script, reads the report, and gives you a short summary.

### Option B — Run the script yourself

From the skill folder:

```bash
python scripts/explain_flows.py "<path-to-solution.zip-or-folder>"
```

By default the report is **auto-named after the solution** and saved next to the source,
e.g. `MySolution-flow-report.md`.

---

## Command-line options

| Option | Description |
|--------|-------------|
| `source` (required) | Path to a solution `.zip` **or** an already-unzipped solution folder. |
| `--output <file>`, `-o <file>` | Write the report to a specific path instead of the auto-named default. |
| `--print` | Print the report to the screen instead of saving a file. |
| `--technical` | Additionally show raw file names and raw API step types. |

### Examples

```bash
# Auto-named report next to the zip
python scripts/explain_flows.py "C:\Downloads\MySolution_managed.zip"

# Save to a chosen path
python scripts/explain_flows.py "C:\Downloads\MySolution_managed.zip" --output "C:\Reports\flows.md"

# Print to the terminal instead of saving
python scripts/explain_flows.py ".\UnpackedSolution" --print

# Include raw technical identifiers for deeper inspection
python scripts/explain_flows.py "C:\Downloads\MySolution_managed.zip" --technical
```

---

## Notes & limitations

- The script is **read-only** — it never modifies your solution.
- Classic workflows / business rules (`.xaml`) are intentionally **skipped**; this skill is
  about **cloud flows** (`.json`). The report tells you how many were skipped.
- Both `.zip` exports and already-unzipped folders are supported.

---

## Files in this skill

| Path | Purpose |
|------|---------|
| `SKILL.md` | Skill definition and instructions Copilot follows. |
| `scripts/explain_flows.py` | The report generator. |
| `references/solution-structure.md` | Background on solution file layout, connection references, and action types — read only when explaining tricky flows. |
| `README.md` | This file. |
