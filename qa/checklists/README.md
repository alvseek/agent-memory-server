# Checklists

Per-feature, **ephemeral** manual-verification plans — created when a specific feature ships, run during QA, archived on sign-off. (Distinct from the evergreen runbook "how to run".)

**Lifecycle**: create on ship (`qa/checklists/{feature}.md`) → run + tick + note defects inline → move to `completed/` on sign-off.

Content shape:
```markdown
# {Feature} — QA Checklist

> Per-feature verification for {feature/plan}. Tick as you go; note defects inline; archive to completed/ on sign-off.

## Preconditions
<bring the stack up via qa/runbooks/munnin.md>

## Checks
- [ ] <observable behavior + expected result>

## Result
<sign-off + date, or defects found>
```
