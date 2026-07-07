# JARVIS Claude Code Development System

## Setup

### Option 1: Drop-in (Recommended)

Copy the entire structure into your JARVIS project root:

```bash
# From your JARVIS project directory
cp -r jarvis-claude-code/.  .claude/

# The main prompt goes to project root
cp CLAUDE.md ./CLAUDE.md
```

Final structure:
```
jarvis/
├── CLAUDE.md                    ← Main system prompt (Claude Code reads this automatically)
├── .claude/
│   ├── agents/
│   │   ├── planner.md           ← Feature planning agent
│   │   ├── architect.md         ← Architecture decisions
│   │   ├── tdd-guide.md         ← Test-driven development
│   │   ├── code-reviewer.md     ← Code review checklist
│   │   └── security-reviewer.md ← Security scanning
│   ├── skills/
│   │   ├── financial-patterns.md ← Romanian accounting, double-entry, VAT
│   │   ├── backend-patterns.md   ← FastAPI, SQLAlchemy, async patterns
│   │   └── continuous-learning.md ← Session debrief, pattern extraction
│   ├── commands/
│   │   └── (slash commands referenced in CLAUDE.md)
│   └── rules/
│       ├── coding-standards.md  ← Python style, naming, types
│       ├── git-workflow.md      ← Commit messages, branching
│       └── testing.md           ← Coverage thresholds, fixtures, naming
└── [your code here]
```

### Option 2: Claude Code Project Settings

If using Claude Code's project settings:
1. Open Claude Code in your JARVIS directory
2. It will automatically read `CLAUDE.md` from project root
3. Reference agent/skill files with: "Follow the planner agent protocol from .claude/agents/planner.md"

## Usage

### Starting a Feature
```
Plan and implement [feature description].
Follow the planner agent, then TDD agent, then code review agent.
```

### Quick Implementation
```
Add [specific thing] to [module]. Follow JARVIS standards.
```

### Code Audit
```
Review [module] against the code review agent checklist.
```

### Post-Session Learning
```
Run the continuous learning skill for this session.
```

## How It Works

The `CLAUDE.md` file contains the complete context Claude Code needs:
- Project structure and tech stack
- Module ownership boundaries (who owns what data)
- Golden rules (immutability, audit trails, GL balance, etc.)
- Agent delegation model (plan → build → test → review)
- Domain knowledge (Romanian accounting, VAT, e-Factura)
- Coding standards, git workflow, testing requirements

The agent/skill/rule files provide deep-dive reference material that Claude Code can consult when working on specific aspects.

Claude Code reads `CLAUDE.md` automatically. The supporting files in `.claude/` are referenced when deeper context is needed for specific tasks.
