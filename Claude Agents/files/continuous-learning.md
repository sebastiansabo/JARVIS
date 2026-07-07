# Continuous Learning Skill

## Purpose
After completing any development task, extract reusable patterns, lessons, and conventions to improve future development sessions.

## Extraction Process

### 1. Pattern Recognition
After each completed feature, identify:
- **New code patterns** that solved a problem elegantly
- **Anti-patterns** that caused bugs or confusion
- **Performance discoveries** (query optimizations, caching strategies)
- **Integration learnings** (API quirks, rate limit behaviors, error formats)

### 2. Convention Evolution
Track emerging conventions:
- If we solved the same type of problem 3+ times, formalize the pattern
- If a naming convention keeps causing confusion, propose an update
- If a test pattern proves reliable, add it to the TDD agent

### 3. Error Catalog Maintenance
For every new error encountered:
```
Error: [ExactErrorType]
Context: [When does this occur?]
Root Cause: [Why does it happen?]
Fix: [How to resolve]
Prevention: [How to avoid in future]
```

### 4. Knowledge Base Update
After each session, consider updates to:
- `CLAUDE.md` — New golden rules, architecture decisions
- `agents/*.md` — Improved checklists, new patterns
- `skills/*.md` — Domain knowledge additions
- `rules/*.md` — New coding standards or conventions

## Session Debrief Template

```
## Session: [Date] — [Feature/Task]

### What Worked
- [Pattern/approach that was effective]

### What Didn't Work
- [Approach that failed] → [Why] → [Better alternative]

### New Patterns Discovered
- [Pattern name]: [Description] → [Where to apply]

### Conventions to Formalize
- [Convention]: [Rationale]

### Knowledge Gaps Identified
- [Topic]: [What we need to learn]
```

## Auto-Extract Triggers
Run this skill when:
- A feature is completed and tests pass
- A bug is fixed (capture root cause and prevention)
- A performance issue is resolved (capture the optimization)
- An integration with an external API is established (capture API behaviors)
- A code review reveals a systemic issue (capture the pattern to avoid)
