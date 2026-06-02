#!/usr/bin/env python3
"""
explain_flows.py
Read an exported Dataverse / Power Platform solution (.zip or an already-unzipped folder),
find the Power Automate cloud flows under Workflows/, and produce a BEGINNER-FRIENDLY
Markdown report: an overview table, and per-flow "At a glance" summary, trigger, connectors,
what kind of work it does, child flows (by name), and the connector operations it performs.

Usage:
    python explain_flows.py <solution.zip | unzipped_folder> [--output report.md]
    python explain_flows.py <...> --technical   # also show raw API ids / operation ids

The script reads only the flow definitions; it never modifies the solution.
"""
import argparse
import json
import os
import re
import sys
import zipfile
from collections import Counter

# --- Friendly names for common connectors (api.name -> display name) -----------------
CONNECTOR_NAMES = {
    "shared_commondataserviceforapps": "Microsoft Dataverse",
    "shared_commondataservice": "Common Data Service (legacy)",
    "shared_office365": "Office 365 Outlook",
    "shared_office365users": "Office 365 Users",
    "shared_office365groups": "Office 365 Groups",
    "shared_sharepointonline": "SharePoint",
    "shared_teams": "Microsoft Teams",
    "shared_approvals": "Approvals",
    "shared_flowmanagement": "Power Automate Management",
    "shared_powerplatformforadmins": "Power Platform for Admins",
    "shared_powerplatformadminv2": "Power Platform Admin (v2)",
    "shared_powerappsforappmakers": "Power Apps for Makers",
    "shared_powervirtualagents": "Copilot Studio (Power Virtual Agents)",
    "shared_azureappinsights": "Azure Application Insights",
    "shared_applicationinsights": "Azure Application Insights",
    "shared_webcontents": "HTTP with Microsoft Entra ID",
    "shared_onedriveforbusiness": "OneDrive for Business",
    "shared_excelonlinebusiness": "Excel Online (Business)",
    "shared_sql": "SQL Server",
    "shared_aibuilder": "AI Builder",
    "shared_http": "HTTP",
}

# --- Trigger type -> plain-English meaning -------------------------------------------
TRIGGER_MEANINGS = {
    "Recurrence": "Runs on a schedule",
    "Request": "Started manually, by a Power App, or by an HTTP request",
    "Manual": "Started manually or by a Power App",
    "OpenApiConnection": "Started by a connector event",
    "OpenApiConnectionWebhook": "Started by a connector event",
    "ApiConnectionWebhook": "Started by a connector event",
}

# --- Trigger type -> Power Automate flow category ------------------------------------
# Mirrors how Power Automate groups flows in its UI: Automated / Instant / Scheduled.
CATEGORY_ORDER = ["Automated", "Instant", "Scheduled", "Other"]
CATEGORY_INFO = {
    "Automated": ("⚡ Automated", "start automatically when an event happens"),
    "Instant": ("👉 Instant", "started on demand — manually, by a Power App, or an HTTP request"),
    "Scheduled": ("⏰ Scheduled", "run on a schedule (recurrence)"),
    "Other": ("• Other", "could not be classified"),
}


def classify_flow_type(triggers: dict) -> str:
    if not isinstance(triggers, dict) or not triggers:
        return "Other"
    _name, trig = next(iter(triggers.items()))
    t_type = trig.get("type", "") if isinstance(trig, dict) else ""
    if t_type == "Recurrence":
        return "Scheduled"
    if t_type in ("Request", "Manual"):
        return "Instant"
    if t_type in (
        "OpenApiConnection",
        "OpenApiConnectionWebhook",
        "ApiConnection",
        "ApiConnectionWebhook",
    ):
        return "Automated"
    return "Other"


# --- Action type -> beginner-friendly label ------------------------------------------
ACTION_LABELS = {
    "OpenApiConnection": "Connector call",
    "OpenApiConnectionWebhook": "Connector call",
    "ApiConnection": "Connector call",
    "Workflow": "Calls another flow",
    "If": "Decision (if / else)",
    "Switch": "Decision (switch)",
    "Foreach": "Loop (for each)",
    "Until": "Loop (until)",
    "Scope": "Group of steps",
    "Compose": "Build a value",
    "InitializeVariable": "Work with a variable",
    "SetVariable": "Work with a variable",
    "AppendToArrayVariable": "Work with a variable",
    "IncrementVariable": "Work with a variable",
    "ParseJson": "Read JSON data",
    "Query": "Filter data",
    "Select": "Reshape data",
    "Join": "Join data",
    "Response": "Return a response",
    "Terminate": "Stop the flow",
    "Http": "Call a web service (HTTP)",
    "Table": "Build a table",
}

# --- Common Dataverse / connector operationIds -> friendly phrase ---------------------
OPERATION_LABELS = {
    "CreateRecord": "Create a row",
    "ListRecords": "List rows",
    "ListRecordsWithOrganization": "List rows",
    "GetItem": "Get a row",
    "GetRecord": "Get a row",
    "UpdateRecord": "Update a row",
    "UpdateOnlyRecord": "Update a row",
    "DeleteRecord": "Delete a row",
    "PerformBoundAction": "Run a Dataverse action",
    "PerformBoundActionWithOrganization": "Run a Dataverse action",
    "PerformUnboundAction": "Run a Dataverse action",
    "AssociateEntities": "Relate rows",
    "DisassociateEntities": "Unrelate rows",
}


def humanize(text: str) -> str:
    """Turn 'When_an_action_is_performed:_Delete_Case' into readable text."""
    if not text:
        return ""
    out = text.replace("_", " ")
    out = re.sub(r"\s*:\s*", ": ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def split_camel(text: str) -> str:
    """Split 'UserProfile_V2' / 'PerformBoundAction' into spaced words where possible."""
    s = text.replace("_", " ")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    return s.strip()


def friendly_connector(api_name: str) -> str:
    key = (api_name or "").strip()
    if key in CONNECTOR_NAMES:
        return CONNECTOR_NAMES[key]
    cleaned = re.sub(r"^shared_", "", key)
    cleaned = cleaned.replace("_", " ").strip()
    return cleaned.title() if cleaned else (api_name or "Unknown connector")


def normalize_conn_key(conn_key: str) -> str:
    """Drop a trailing '-1' / '_1' instance suffix from a connection key."""
    if not conn_key:
        return ""
    return re.sub(r"[-_]\d+$", "", conn_key)


def friendly_operation(operation_id: str) -> str:
    if not operation_id:
        return "Operation"
    if operation_id in OPERATION_LABELS:
        return OPERATION_LABELS[operation_id]
    return split_camel(operation_id)


def flow_display_name(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename))[0]
    base = re.sub(
        r"-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$",
        "",
        base,
    )
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", base)
    return spaced.strip() or base


def flow_guid(filename: str):
    m = re.search(
        r"-([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\.json$",
        filename,
    )
    return m.group(1).lower() if m else None


def walk_actions(actions: dict, stats: dict):
    if not isinstance(actions, dict):
        return
    for name, action in actions.items():
        if not isinstance(action, dict):
            continue
        a_type = action.get("type", "Unknown")
        stats["type_counter"][a_type] += 1
        stats["total_actions"] += 1

        inputs = action.get("inputs", {}) if isinstance(action.get("inputs"), dict) else {}
        host = inputs.get("host", {}) if isinstance(inputs.get("host"), dict) else {}

        if a_type in ("OpenApiConnection", "OpenApiConnectionWebhook", "ApiConnection"):
            conn_key = host.get("connectionName") or host.get("connection") or host.get("apiId")
            operation = host.get("operationId", "")
            params = inputs.get("parameters", {})
            entity = params.get("entityName") if isinstance(params, dict) else None
            stats["connector_calls"].append((conn_key, operation, entity))
        elif a_type == "Workflow":
            stats["child_flow_guids"].append(str(host.get("workflowReferenceName", "")).lower())

        for nested_key in ("actions", "else", "default"):
            nested = action.get(nested_key)
            if isinstance(nested, dict):
                walk_actions(nested.get("actions", nested), stats)
        cases = action.get("cases")
        if isinstance(cases, dict):
            for case in cases.values():
                if isinstance(case, dict):
                    walk_actions(case.get("actions", {}), stats)


def describe_trigger(triggers: dict):
    """Return (short_meaning, full_label)."""
    if not isinstance(triggers, dict) or not triggers:
        return "No trigger", "No trigger found"
    name, trig = next(iter(triggers.items()))
    t_type = trig.get("type", "Unknown") if isinstance(trig, dict) else "Unknown"
    kind = trig.get("kind", "") if isinstance(trig, dict) else ""

    # For instant (Request) flows, the 'kind' tells us how it's actually started.
    if t_type == "Request":
        meaning = {
            "Button": "Started manually (button / Run)",
            "PowerAppV2": "Started by a Power App",
            "PowerApp": "Started by a Power App",
            "Skills": "Started by a Copilot Studio agent",
            "Http": "Started by an HTTP request",
        }.get(kind, "Started manually, by a Power App, or by an HTTP request")
    else:
        meaning = TRIGGER_MEANINGS.get(t_type, split_camel(t_type))

    detail = ""
    if t_type == "Recurrence" and isinstance(trig, dict):
        rec = trig.get("recurrence", {}) or {}
        freq = rec.get("frequency", "")
        interval = rec.get("interval", "")
        if freq:
            detail = f" (every {interval} {str(freq).lower()})"
    full = f"{meaning}{detail} — *{humanize(name)}*"
    return meaning + detail, full


def analyze_flow(filename, text):
    obj = json.loads(text)
    props = obj.get("properties", {})
    definition = props.get("definition", {})
    conn_refs = props.get("connectionReferences", {}) or {}

    stats = {
        "type_counter": Counter(),
        "total_actions": 0,
        "connector_calls": [],
        "child_flow_guids": [],
    }
    walk_actions(definition.get("actions", {}), stats)

    # Map connection keys -> friendly connector name using connectionReferences.
    key_to_friendly = {}
    declared_connectors = set()
    for key, ref in conn_refs.items():
        api = (ref.get("api", {}) or {}).get("name", "")
        friendly = friendly_connector(api)
        key_to_friendly[key] = friendly
        key_to_friendly[normalize_conn_key(key)] = friendly
        declared_connectors.add(friendly)

    # Connectors actually used in actions (more accurate than "declared"), with their
    # operations grouped by connector, plus the Dataverse tables touched.
    used_connectors = set()
    ops_by_connector = {}  # friendly_connector -> set of friendly operation labels
    tables = set()
    for conn_key, op, entity in stats["connector_calls"]:
        friendly_conn = (
            key_to_friendly.get(conn_key)
            or key_to_friendly.get(normalize_conn_key(conn_key))
            or friendly_connector(conn_key)
        )
        used_connectors.add(friendly_conn)
        ops_by_connector.setdefault(friendly_conn, set()).add(friendly_operation(op))
        if entity and friendly_conn == "Microsoft Dataverse":
            # Only keep literal table names, not dynamic expressions like @items(...).
            if not str(entity).lstrip().startswith("@"):
                tables.add(str(entity))

    connectors = sorted(used_connectors or declared_connectors)
    ops_by_connector = {c: sorted(v) for c, v in ops_by_connector.items()}

    short_trigger, full_trigger = describe_trigger(definition.get("triggers", {}))

    return {
        "file": os.path.basename(filename),
        "name": flow_display_name(filename),
        "guid": flow_guid(filename),
        "category": classify_flow_type(definition.get("triggers", {})),
        "short_trigger": short_trigger,
        "full_trigger": full_trigger,
        "connectors": connectors,
        "ops_by_connector": ops_by_connector,
        "tables": sorted(tables),
        "type_counter": stats["type_counter"],
        "total_actions": stats["total_actions"],
        "child_flow_counts": Counter(g for g in stats["child_flow_guids"] if g),
    }


def complexity_label(total_actions):
    if total_actions <= 5:
        return "Small"
    if total_actions <= 20:
        return "Medium"
    return "Large"


def at_a_glance(fl):
    parts = [f"**{fl['category']}** flow — {complexity_label(fl['total_actions']).lower()} ({fl['total_actions']} steps)."]
    if fl["connectors"]:
        parts.append("Works with " + ", ".join(fl["connectors"]) + ".")
    else:
        parts.append("Uses only built-in actions (no external connectors).")
    unique_children = len(fl["child_flow_counts"])
    if unique_children:
        total_calls = sum(fl["child_flow_counts"].values())
        if total_calls == unique_children:
            parts.append(f"Calls {unique_children} child flow(s).")
        else:
            parts.append(f"Calls {unique_children} child flow(s), {total_calls} times total.")
    return " ".join(parts)


def logic_summary(type_counter):
    """Keep only decision-useful logic categories; fold plumbing into one phrase."""
    connector_calls = type_counter.get("OpenApiConnection", 0) + type_counter.get(
        "OpenApiConnectionWebhook", 0
    ) + type_counter.get("ApiConnection", 0)
    loops = type_counter.get("Foreach", 0) + type_counter.get("Until", 0)
    decisions = type_counter.get("If", 0) + type_counter.get("Switch", 0)
    child_calls = type_counter.get("Workflow", 0)
    http_calls = type_counter.get("Http", 0)

    bits = []
    if connector_calls:
        bits.append(f"{connector_calls} connector action(s)")
    if http_calls:
        bits.append(f"{http_calls} web (HTTP) call(s)")
    if loops:
        bits.append(f"{loops} loop(s)")
    if decisions:
        bits.append(f"{decisions} decision(s)")
    if child_calls:
        bits.append(f"{child_calls} child-flow call(s)")

    # Anything else counts as internal data-prep plumbing.
    meaningful_types = {
        "OpenApiConnection",
        "OpenApiConnectionWebhook",
        "ApiConnection",
        "Foreach",
        "Until",
        "If",
        "Switch",
        "Workflow",
        "Http",
    }
    other = sum(n for t, n in type_counter.items() if t not in meaningful_types)
    if other:
        bits.append(f"plus {other} internal data-prep step(s)")

    return ", ".join(bits) if bits else "no significant logic"


def friendly_step_breakdown(type_counter):
    grouped = Counter()
    for t, n in type_counter.items():
        grouped[ACTION_LABELS.get(t, split_camel(t))] += n
    return ", ".join(f"{label} × {n}" for label, n in grouped.most_common())


def slugify(text, used):
    base = re.sub(r"[^a-z0-9\s-]", "", text.lower()).strip()
    base = re.sub(r"\s+", "-", base)
    slug = base or "flow"
    final = slug
    i = 1
    while final in used:
        i += 1
        final = f"{slug}-{i}"
    used.add(final)
    return final


def build_report(source, flows, skipped_xaml, guid_index, technical=False):
    L = []
    L.append(f"# Cloud Flow Report — {os.path.basename(source)}")
    L.append("")
    L.append(f"- **Cloud flows analyzed:** {len(flows)}")
    if skipped_xaml:
        L.append(f"- **Classic workflows / business rules skipped (.xaml):** {skipped_xaml}")

    all_connectors = Counter()
    for fl in flows:
        for c in fl["connectors"]:
            all_connectors[c] += 1
    if all_connectors:
        L.append("- **Connectors used across the solution:**")
        for name, count in all_connectors.most_common():
            L.append(f"  - {name} — used by {count} flow(s)")
    L.append("")

    biggest = sorted(flows, key=lambda x: x["total_actions"], reverse=True)[:5]
    if biggest and biggest[0]["total_actions"] > 0:
        L.append("- **Biggest flows (by number of steps):**")
        for fl in biggest:
            L.append(f"  - {fl['name']} — {fl['total_actions']} steps")
        L.append("")

    # Group flows by Power Automate category (Automated / Instant / Scheduled / Other).
    by_category = {cat: [] for cat in CATEGORY_ORDER}
    for fl in flows:
        by_category.setdefault(fl["category"], []).append(fl)
    present_categories = [c for c in CATEGORY_ORDER if by_category.get(c)]

    L.append("## Flows by type")
    L.append("")
    for cat in present_categories:
        label, desc = CATEGORY_INFO[cat]
        L.append(f"- **{label} — {len(by_category[cat])} flow(s)** ({desc})")
    L.append("")
    L.append("---")
    L.append("")

    # Assign anchors (sorted by name within each category).
    used_slugs = set()
    for cat in present_categories:
        by_category[cat].sort(key=lambda x: x["name"].lower())
        for fl in by_category[cat]:
            fl["_slug"] = slugify(fl["name"], used_slugs)

    # Contents table, grouped by category.
    L.append("## Contents")
    L.append("")
    for cat in present_categories:
        label, _desc = CATEGORY_INFO[cat]
        L.append(f"### {label} ({len(by_category[cat])})")
        L.append("")
        L.append("| Flow | Starts when | Connectors | Steps |")
        L.append("|------|-------------|------------|-------|")
        for fl in by_category[cat]:
            conn = ", ".join(fl["connectors"]) if fl["connectors"] else "—"
            L.append(
                f"| [{fl['name']}](#{fl['_slug']}) | {fl['short_trigger']} | {conn} | {fl['total_actions']} |"
            )
        L.append("")
    L.append("---")
    L.append("")

    # Compute parent/child/standalone role: which flows are called by others.
    referenced_guids = set()
    for fl in flows:
        referenced_guids.update(fl["child_flow_counts"].keys())

    # Detail sections, also grouped by category.
    for cat in present_categories:
        label, _desc = CATEGORY_INFO[cat]
        L.append(f"# {label} flows")
        L.append("")
        for fl in by_category[cat]:
            L.append(f"## {fl['name']}")
            L.append("")
            L.append(f"> **At a glance:** {at_a_glance(fl)}")
            L.append("")

            L.append(f"- **Starts when:** {fl['full_trigger']}")

            # Role: parent / child / standalone.
            calls_children = bool(fl["child_flow_counts"])
            is_called = fl["guid"] in referenced_guids
            if calls_children and is_called:
                role = "Used by other flows, and also calls child flows of its own"
            elif calls_children:
                role = "Parent flow — calls one or more child flows"
            elif is_called:
                role = "Child flow — run by another flow"
            else:
                role = "Standalone flow"
            L.append(f"- **Role:** {role}")

            # What it does in connected systems, grouped by connector.
            if fl["ops_by_connector"]:
                L.append("- **What it does in connected systems:**")
                for conn in sorted(fl["ops_by_connector"]):
                    actions = ", ".join(fl["ops_by_connector"][conn])
                    L.append(f"  - **{conn}:** {actions}")
            elif fl["connectors"]:
                L.append(f"- **Works with:** {', '.join(fl['connectors'])}")

            # Dataverse tables touched (factual, from connector parameters).
            if fl["tables"]:
                L.append(f"- **Dataverse tables touched:** {', '.join(fl['tables'])}")

            # Child flows, de-duplicated with call counts.
            if fl["child_flow_counts"]:
                L.append("- **Calls these child flows:**")
                for g, count in fl["child_flow_counts"].most_common():
                    child = guid_index.get(g, f"(a flow with id {g})")
                    suffix = f" — called {count} times" if count > 1 else ""
                    L.append(f"  - {child}{suffix}")

            # Logic summary: only decision-useful categories.
            if fl["type_counter"]:
                L.append(f"- **Logic used:** {logic_summary(fl['type_counter'])}")

            if technical:
                raw_types = ", ".join(f"{t} × {n}" for t, n in fl["type_counter"].most_common())
                L.append(f"- _Technical: file `{fl['file']}`; raw step types: {raw_types}_")

            L.append("")

    return "\n".join(L)


def collect_flow_texts(path):
    """Return (items, skipped_xaml) where items is a list of (filename, text)."""
    items = []
    skipped_xaml = 0
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for entry in z.namelist():
                if re.match(r"(?i)^.*workflows/.*\.json$", entry):
                    with z.open(entry) as fh:
                        items.append((entry, fh.read().decode("utf-8-sig")))
                elif re.match(r"(?i)^.*workflows/.*\.xaml$", entry):
                    skipped_xaml += 1
    elif os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            if os.path.basename(root).lower() == "workflows":
                for f in files:
                    full = os.path.join(root, f)
                    if f.lower().endswith(".json"):
                        with open(full, "r", encoding="utf-8-sig") as fh:
                            items.append((f, fh.read()))
                    elif f.lower().endswith(".xaml"):
                        skipped_xaml += 1
    else:
        raise FileNotFoundError(f"Not a zip or folder: {path}")
    return items, skipped_xaml


def default_output_path(source: str) -> str:
    """Derive '<solution-name>-flow-report.md' next to the source zip/folder."""
    source = os.path.abspath(source)
    if os.path.isdir(source):
        parent = os.path.dirname(source.rstrip("\\/"))
        stem = os.path.basename(source.rstrip("\\/"))
    else:
        parent = os.path.dirname(source)
        stem = os.path.splitext(os.path.basename(source))[0]
    # Clean the solution stem for a tidy file name.
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "solution"
    return os.path.join(parent, f"{safe}-flow-report.md")


def main():
    parser = argparse.ArgumentParser(
        description="Explain the cloud flows inside a Dataverse / Power Platform solution."
    )
    parser.add_argument("source", help="Path to a solution .zip or an unzipped solution folder")
    parser.add_argument(
        "--output",
        "-o",
        help="Where to write the Markdown report. "
        "If omitted, it is named after the solution, e.g. 'MySolution-flow-report.md', "
        "and saved next to the source.",
    )
    parser.add_argument(
        "--print", dest="to_stdout", action="store_true", help="Print the report instead of saving a file"
    )
    parser.add_argument(
        "--technical", action="store_true", help="Also include raw file names and API step types"
    )
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"ERROR: path not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    items, skipped_xaml = collect_flow_texts(args.source)
    if not items:
        print("No cloud flows (.json) found under a Workflows/ folder.", file=sys.stderr)
        sys.exit(2)

    # Build GUID -> flow display name index so we can name child flows.
    guid_index = {}
    for filename, _text in items:
        g = flow_guid(filename)
        if g:
            guid_index[g] = flow_display_name(filename)

    flows, errors = [], []
    for filename, text in items:
        try:
            flows.append(analyze_flow(filename, text))
        except Exception as exc:  # noqa: BLE001
            errors.append((filename, str(exc)))

    if not flows:
        print("Found flow files, but none could be parsed.", file=sys.stderr)
        sys.exit(2)

    report = build_report(args.source, flows, skipped_xaml, guid_index, technical=args.technical)

    if args.to_stdout:
        print(report)
    else:
        out_path = args.output or default_output_path(args.source)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Report written to {out_path}  ({len(flows)} flows)")

    if errors:
        print(f"\n[note] {len(errors)} flow file(s) could not be parsed:", file=sys.stderr)
        for fn, err in errors:
            print(f"  - {fn}: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
