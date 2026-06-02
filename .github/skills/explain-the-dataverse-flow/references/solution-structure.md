# Reference: How cloud flows are stored in a Dataverse solution

> Read this only when you need to understand or debug the flow file format. For a normal
> run, `scripts/explain_flows.py` already handles all of this.

## Where flows live

When you export a Dataverse / Power Platform solution, you get a `.zip`. Inside it:

```
SolutionName.zip
├── [Content_Types].xml
├── solution.xml
├── customizations.xml
└── Workflows/
    ├── MyCloudFlow-<GUID>.json     ← a modern cloud flow (Power Automate)
    ├── AnotherFlow-<GUID>.json
    └── SomeBusinessRule-<GUID>.xaml ← a CLASSIC workflow / business rule (not a cloud flow)
```

- **`.json`** files = **modern cloud flows**. This is what the skill explains.
- **`.xaml`** files = classic workflows, business rules, dialogs. The skill skips these.
- The file name is `<FlowName>-<GUID>.json`. The display name is derived from the part
  before the GUID.

## Anatomy of a cloud flow `.json`

```jsonc
{
  "properties": {
    "connectionReferences": {
      "shared_commondataserviceforapps-1": {
        "api": { "name": "shared_commondataserviceforapps" },
        "connection": { "connectionReferenceLogicalName": "cat_MyDataverseConnRef" },
        "runtimeSource": "embedded"
      }
    },
    "definition": {
      "$schema": "https://schema.management.azure.com/.../workflowdefinition.json#",
      "triggers": { "Recurrence": { "type": "Recurrence", "recurrence": { "frequency": "Day", "interval": 1 } } },
      "actions": {
        "Run_a_Child_Flow": { "type": "Workflow", "inputs": { "host": { "workflowReferenceName": "<GUID>" } } }
      }
    },
    "templateName": ""
  },
  "schemaVersion": "1.0.0.0"
}
```

### Connectors → `properties.connectionReferences`
Each entry maps a connection key to:
- `api.name` — the connector's API id, e.g. `shared_commondataserviceforapps`
  (= **Microsoft Dataverse**), `shared_office365` (= **Office 365 Outlook**).
- `connection.connectionReferenceLogicalName` — the connection reference used at deploy time.

### Trigger → `properties.definition.triggers`
A single trigger object keyed by name. Common `type` values:
| `type` | `kind` | Flow category (Power Automate UI) | Meaning |
|---|---|---|---|
| `Recurrence` | — | **Scheduled** | Runs on a schedule (see `recurrence.frequency`/`interval`) |
| `Request` | `Button` | **Instant** | Started manually (Run button) |
| `Request` | `PowerAppV2` | **Instant** | Started by a Power App |
| `Request` | `Skills` | **Instant** | Started by a Copilot Studio agent |
| `Request` | `Http` | **Instant** | Started by an HTTP request |
| `OpenApiConnection(Webhook)` | — | **Automated** | Started by a connector event/webhook |

> Microsoft documents exactly three cloud-flow categories — a flow is triggered
> **automatically** (Automated), **instantly** (Instant), or **via a schedule** (Scheduled).
> See https://learn.microsoft.com/power-automate/flow-types and
> https://learn.microsoft.com/power-automate/overview-cloud. The report groups flows using
> these same three categories, derived from the trigger `type`/`kind` above.

### Steps → `properties.definition.actions`
A tree of actions keyed by name. Each action has a `type`. Important ones:
| `type` | Meaning |
|---|---|
| `OpenApiConnection` | A **connector call**. `inputs.host.connectionName` → a key in `connectionReferences`; `inputs.host.operationId` → the operation (e.g. `CreateRecord`). |
| `Workflow` | Calls a **child flow**. `inputs.host.workflowReferenceName` is the child's GUID. |
| `Scope`, `If`, `Foreach`, `Until`, `Switch` | **Control actions** that contain *nested* `actions` (and `else` / `cases`). Must be walked recursively. |
| `Compose`, `InitializeVariable`, `SetVariable`, `ParseJson`, `Query`, `Response`, `Terminate` | Built-in / data actions (no external connector). |

## Why recursion matters
Connector calls are often **nested** inside `Scope` (Try/Catch/Finally), `If`, or `Foreach`
blocks. A parser that only looks at top-level actions will miss them, so the script walks the
whole tree, including `else` branches and `switch` cases.

## Notes / caveats
- The display name is derived from the file name, not a localized label, so it may differ
  slightly from what you see in the Power Automate UI.
- Child flows are identified by GUID; the script reports how many a flow calls. You can match
  the GUID to another file in `Workflows/` to see which flow it is.
- Some exports (e.g. `pac solution unpack` or Git source control) may present flow content
  differently; this skill targets the standard solution-export `.zip` layout described above.
