---
name: explain-the-dataverse-flow
description: Explains the Power Automate cloud flows inside an exported Dataverse / Power Platform solution by reading the solution .zip (or unpacked solution folder) and producing a clear, beginner-friendly report of each flow's purpose, trigger, connectors used, action steps, and child flows. Use this whenever the user has a Dataverse or Power Platform solution export and wants to understand, document, review, or summarize the cloud flows inside it — even if they just say "what do these flows do", "summarize my solution's flows", "explain this exported solution", or "make these exported flows readable".
---

# Explain the Dataverse Flow

Exported Power Platform solutions store each cloud flow as a large machine-format file under
the `Workflows/` folder. These are hard for a human to read. This skill turns them into a
clean, readable report.

## When to use this

Use this skill when the user points you at:
- a **solution `.zip`** exported from Dataverse / Power Platform, **or**
- an **unpacked solution folder** (one that contains a `Workflows/` directory).

…and wants to **understand, document, review, or summarize** the cloud flows inside it.

## What it produces

A **beginner-friendly** Markdown report with:
- A **solution summary**: how many cloud flows, which connectors are used across them, and
  the biggest flows by step count.
- A **Flows by type** count (Automated / Instant / Scheduled / Other) and a **Contents
  table** linking to every flow, grouped by type.
- Per flow: an **"At a glance"** plain-English summary, **what starts it** (trigger), the
  flow's **Role** (Parent / Child / Standalone), **what it does in connected systems**
  (operations grouped by friendly connector name), the **Dataverse tables touched**, the
  **child flows it calls** (de-duplicated with counts), and a concise **Logic used** line.

The report deliberately avoids raw internal identifiers (e.g. `OpenApiConnection`,
`shared_commondataserviceforapps`) in the main view. Pass `--technical` if you also want the
raw file names and API step types.

## How to run it

Run the bundled script and point it at the solution. It reads the flows only — it never
modifies the solution.

```bash
python scripts/explain_flows.py "<path-to-solution.zip-or-folder>"
```

- By default the report is **auto-named after the solution** (e.g. `MySolution-flow-report.md`).
- Pass `--output <file>` to save the report to a specific path, or `--print` to print it to the screen instead.
- Pass `--technical` to additionally show raw file names and raw API step types.
- The script accepts either a `.zip` or an already-unzipped folder.
- Classic workflows / business rules (`.xaml`) are intentionally skipped — this skill is
  about **cloud flows** (`.json`).

After running, read the generated report and give the user a short plain-language summary:
which flows look important, what external systems they touch (connectors), and how they are
triggered. Offer to drill into any single flow in more detail.

## How flows are stored (background)

If you need to understand the file layout, the connection-reference mapping, or the action
types before explaining a tricky flow, read `references/solution-structure.md`. Load it only
when needed — for a normal run you don't need it.

## Example

**Input:** `python scripts/explain_flows.py "CopilotStudioKit_managed.zip"`

**Output (excerpt):**
```
## Agent Compliance Execute Policy Action

> At a glance: Automated flow — medium (18 steps). Works with Microsoft Dataverse,
> Office 365 Users.

- Starts when: Started by a connector event — When an action is performed: Enforce Action policy
- Role: Standalone flow
- What it does in connected systems:
  - Microsoft Dataverse: Create a row, Get a row, List rows, Run a Dataverse action, Update a row
  - Office 365 Users: User Profile V2
- Dataverse tables touched: annotations, cat_actionpolicies, cat_compliancecases
- Logic used: 10 connector action(s), 1 decision(s), plus 7 internal data-prep step(s)
```
