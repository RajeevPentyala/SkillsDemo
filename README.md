# SkillsDemo

A collection of custom **GitHub Copilot CLI skills**.

Skills live under [`.github/skills/`](.github/skills/) and extend Copilot with
specialized, repeatable workflows.

## Skills

| Skill | Description |
|-------|-------------|
| [explain-the-dataverse-flow](.github/skills/explain-the-dataverse-flow/README.md) | Reads an exported Dataverse / Power Platform solution (`.zip` or unpacked folder) and produces a clear, beginner-friendly Markdown report of every Power Automate cloud flow — its purpose, trigger, connectors, steps, and child flows. |

## Repository layout

```
.github/
└── skills/
    └── explain-the-dataverse-flow/
        ├── SKILL.md          # Skill definition Copilot follows
        ├── README.md         # How to use this skill
        ├── scripts/          # Supporting scripts
        └── references/       # Background reference docs
```

## Using a skill

Open the GitHub Copilot CLI in this repository and ask Copilot to perform the task — it
will load the relevant skill automatically. See each skill's own README for details and
examples.
