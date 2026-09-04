# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Repo state

`gacherubini/CRM` currently carries only GitHub's default label set, of which
`wontfix` already matches this table — reuse it, don't create a duplicate.

The other four (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`)
do not exist yet. Create one the first time `/triage` needs it:

```
gh label create needs-triage --description "Maintainer needs to evaluate this issue"
```

Check with `gh label list` before creating, so a rename done in the GitHub UI
doesn't turn into a second, near-identical label.
