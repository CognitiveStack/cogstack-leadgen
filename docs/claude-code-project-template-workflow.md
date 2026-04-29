
# Claude Code Project Template

A structured template for building applications with Claude Code using the **PIV Loop** workflow (Prime → Implement → Validate).

This template provides slash commands, reference documentation, and best practices for AI-assisted development.

---

## What's Included

```
.claude/
├── commands/
│   ├── core_piv_loop/       # Prime, plan, execute commands
│   ├── validation/          # Code review, testing, reports
│   ├── github_bug_fix/      # RCA and bug fix workflow
│   ├── commit.md            # Atomic commit helper
│   ├── create-prd.md        # PRD generator
│   └── init-project.md      # Project initialization
├── reference/
│   ├── fastapi-best-practices.md
│   ├── caddy-patterns.md
│   ├── uv-python-workflow.md
│   ├── deployment-best-practices.md
│   ├── sqlite-best-practices.md
│   ├── react-frontend-best-practices.md
│   └── testing-and-logging.md
└── PRD.md                   # Product Requirements Document
```

---

## Quick Start

### Option A: New Project (GitHub Template) ⭐ Recommended

The easiest way — creates a fresh repository with no git history from this template.

1. **Click "Use this template"** (green button at top of this repo)
2. **Select "Create a new repository"**
3. **Name your repository** and choose public/private
4. **Click "Create repository"**

You now have a clean copy with its own git history. Clone and start building:

```bash
git clone https://github.com/YOUR_USERNAME/your-new-project.git
cd your-new-project
claude  # Start Claude Code
```

---

### Option B: New Project (Manual Clone)

If you prefer command-line or need more control:

```bash
# 1. Clone the template
git clone https://github.com/journeyman33/claude-code-template.git my-new-project
cd my-new-project

# 2. Remove git history and start fresh
rm -rf .git
git init
git add .
git commit -m "Initial commit from Claude Code template"

# 3. Create your GitHub repo and push
gh repo create my-new-project --public --source=. --push
# Or manually:
# git remote add origin https://github.com/YOUR_USERNAME/my-new-project.git
# git push -u origin main

# 4. Start Claude Code
claude
```

---

### Option C: Existing Project

Add the Claude Code workflow to a repository you already have.

```bash
# 1. Clone the template temporarily
git clone --depth 1 \
  https://github.com/journeyman33/claude-code-template.git /tmp/claude-template

# 2. Copy the .claude directory to your project
cp -r /tmp/claude-template/.claude /path/to/your/project/

# 3. Copy the CLAUDE.md template
cp /tmp/claude-template/CLAUDE.template.md /path/to/your/project/CLAUDE.md

# 4. Clean up
rm -rf /tmp/claude-template

# 5. Customize CLAUDE.md for your project
cd /path/to/your/project
# Edit CLAUDE.md with your project details

# 6. Commit
git add .claude/ CLAUDE.md
git commit -m "feat: add Claude Code workflow"
```

---

## The PIV Loop Workflow

This template follows the **PIV Loop** — a structured approach to AI-assisted development:

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│    ┌─────────┐     ┌─────────────┐     ┌──────────┐    │
│    │  PRIME  │ ──► │  IMPLEMENT  │ ──► │ VALIDATE │    │
│    └─────────┘     └─────────────┘     └──────────┘    │
│         │                                    │          │
│         └────────────────────────────────────┘          │
│                      (iterate)                          │
└─────────────────────────────────────────────────────────┘
```

| Phase | What Happens | Commands |
|-------|--------------|----------|
| **Prime** | Load context, understand codebase | `/core_piv_loop:prime` |
| **Implement** | Plan and execute features | `/core_piv_loop:plan-feature`, `/core_piv_loop:execute` |
| **Validate** | Test, review, document | `/validation:validate`, `/validation:code-review` |

---

## Step-by-Step: Building a New Project

### Step 1: Define Your Project

Start a conversation with Claude Code about what you want to build.

```bash
claude
```

Discuss with Claude:
- What problem does this solve?
- Who is the target user?
- What are the core features (MVP)?
- What tech stack? (FastAPI, React, etc.)

### Step 2: Create Your PRD

Use the `/create-prd` command to generate a Product Requirements Document.

```
/create-prd
```

Claude will ask clarifying questions and generate `.claude/PRD.md` with:
- Project overview
- User stories
- Feature specifications
- Technical requirements
- API design
- Database schema

**Review and refine the PRD** — this is your project blueprint.

### Step 3: Customize CLAUDE.md

Update `CLAUDE.md` with your project specifics:

```markdown
# My Project Name

Brief description of what this project does.

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, SQLite/Postgres
- **Frontend**: React 18, Vite, Tailwind CSS, TanStack Query
- **Testing**: pytest, Playwright

## Project Structure

(Fill in once scaffolded)

## Commands

(Add your specific dev commands)

## Reference Documentation

| Document | When to Read |
|----------|--------------|
| `.claude/PRD.md` | Understanding requirements |
| `.claude/reference/fastapi-best-practices.md` | Building API endpoints |
| ... | ... |
```

### Step 4: Prime Claude

Load the project context:

```
/core_piv_loop:prime
```

This command tells Claude to:
- Read `CLAUDE.md`
- Read `.claude/PRD.md`
- Understand the codebase structure
- Load relevant reference docs

### Step 5: Plan Your First Feature

Pick a feature from your PRD and create an implementation plan:

```
/core_piv_loop:plan-feature
```

Claude will:
- Analyze the codebase
- Break down the feature into tasks
- Create a step-by-step implementation plan
- Save the plan to `.claude/plans/`

### Step 6: Execute the Plan

Implement the feature step-by-step:

```
/core_piv_loop:execute
```

Claude will:
- Work through each task in the plan
- Write code following the reference docs
- Create tests as it goes
- Ask for confirmation at key points

### Step 7: Validate

After implementation, run validation:

```
/validation:validate
```

This runs:
- Linting (ruff)
- Type checking
- Unit tests
- Integration tests
- Build verification

### Step 8: Code Review

Get a technical review of your changes:

```
/validation:code-review
```

Fix any issues:

```
/validation:code-review-fix
```

### Step 9: Commit

Create an atomic commit with proper formatting:

```
/commit
```

### Step 10: Repeat

Go back to Step 5 for the next feature. Continue the PIV loop until your MVP is complete.

---

## Command Reference

### Core PIV Loop

| Command | Description |
|---------|-------------|
| `/core_piv_loop:prime` | Load project context and codebase understanding |
| `/core_piv_loop:plan-feature` | Create implementation plan for a feature |
| `/core_piv_loop:execute` | Execute the plan step-by-step |

### Validation

| Command | Description |
|---------|-------------|
| `/validation:validate` | Run full validation suite |
| `/validation:code-review` | Technical review of changed files |
| `/validation:code-review-fix` | Fix issues found in review |
| `/validation:execution-report` | Generate post-implementation report |
| `/validation:system-review` | Analyze implementation vs plan |

### Bug Fixing

| Command | Description |
|---------|-------------|
| `/github_bug_fix:rca` | Create root cause analysis for a GitHub issue |
| `/github_bug_fix:implement-fix` | Implement fix based on RCA |

### Utilities

| Command | Description |
|---------|-------------|
| `/commit` | Create atomic commit with conventional format |
| `/create-prd` | Generate PRD from conversation |
| `/init-project` | Initialize project (install deps, start servers) |

---

## Tech Stack Defaults

This template is configured for:

| Layer | Default | Reference Doc |
|-------|---------|---------------|
| **Backend** | Python 3.12+, FastAPI, UV | `uv-python-workflow.md` |
| **Database** | SQLite (dev) → Postgres (prod) | `sqlite-best-practices.md` |
| **Frontend** | React 18, Vite, Tailwind | `react-frontend-best-practices.md` |
| **Reverse Proxy** | Caddy | `caddy-patterns.md` |
| **Deployment** | Docker Compose | `deployment-best-practices.md` |
| **Testing** | pytest, Playwright | `testing-and-logging.md` |

Customize the reference docs for your preferred stack.

---

## Adding Reference Documents

The `.claude/reference/` directory contains best practices guides. Claude reads these when working on specific areas.

To add your own:

1. Create a markdown file in `.claude/reference/`
2. Follow the existing format (table of contents, code examples, anti-patterns)
3. Reference it in `CLAUDE.md`

Example custom references:
- `supabase-patterns.md` — Your Supabase integration patterns
- `n8n-webhooks.md` — Automation trigger patterns
- `kubernetes-deployment.md` — K8s deployment patterns

---

## Tips for Effective AI-Assisted Development

### Do

- ✅ **Be specific** in your PRD — vague requirements = vague code
- ✅ **Review plans** before executing — catch issues early
- ✅ **Validate frequently** — don't let bugs accumulate
- ✅ **Keep CLAUDE.md updated** — it's Claude's memory
- ✅ **Use reference docs** — they encode your patterns

### Don't

- ❌ **Skip the PRD** — you'll waste time on rework
- ❌ **Execute without a plan** — leads to inconsistent code
- ❌ **Ignore validation failures** — fix them immediately
- ❌ **Let CLAUDE.md get stale** — outdated context = wrong code

---

## Customizing for Your Workflow

### Different Tech Stack?

1. Update reference docs in `.claude/reference/`
2. Modify `CLAUDE.md` template sections
3. Adjust `/init-project.md` for your setup commands

### Different Branching Strategy?

Modify `/commit.md` to match your workflow (GitFlow, trunk-based, etc.)

### Different Testing Approach?

Update `/validation:validate` command to run your test suite.

---

## Resources

- [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)
- [Context Engineering Guide](https://github.com/coleam00/context-engineering-intro)
- [Cole Medin's YouTube](https://www.youtube.com/@ColeMedin) — Original workshop source

---

## Credits

Based on [Cole Medin's AI Coding Workshop](https://github.com/coleam00/habit-tracker) template.

Customized with Caddy, UV, and docker-compose patterns for self-hosted deployments.
