# Plan: Make CLAUDE.md Development Constraints Actionable + Update Phase 1 Scaffolding

## Context

CLAUDE.md mandates TDD/BDD and "Python for Tekton tasks" but doesn't specify frameworks, tools, or test conventions for a repo that is 95% YAML. The migration plan contradicts CLAUDE.md by using inline bash for all Tekton tasks. The sibling `operator-pipelines` repo provides a proven pattern: pytest + tox + yamllint + tekton-lint, with Python CLI tools tested separately from Tekton YAML. These gaps need to be resolved before Phase 1 implementation begins.

## Decision: Tekton Task Script Approach

**All Python from the start**, matching operator-pipelines pattern.

Every Tekton task calls a Python CLI entry point packaged in a custom container image. Even simple tasks (create-namespace, wait-for-condition) are Python — this gives 100% test coverage from day 1 and eliminates the bash-vs-Python decision on every new task. The `pyproject.toml` defines CLI entry points; Tekton tasks are thin YAML that call them.

This aligns with CLAUDE.md's existing "use Python for Tekton task scripts" rule and with operator-pipelines. The migration plan's inline bash will be replaced with Python equivalents.

## Changes

### 1. CLAUDE.md — Update "Tekton Tasks" subsection (line ~81-84)

Replace:
```
### Tekton Tasks

- Use **Python** for Tekton task scripts
- Keep scripts focused and single-purpose
- Handle errors explicitly — fail fast if preconditions aren't met
```

With:
```
### Tekton Tasks

- **All** Tekton task logic lives in Python CLI tools, packaged via `pyproject.toml` entry points
- Tekton Task YAML contains only a thin bash stub that calls the Python CLI entry point
- Python tools are built into a custom pipeline container image (single image for all tasks)
- Scripts: single-purpose, fail fast, 100% pytest coverage required
- Image tag pinned in one place (pipeline param or ConfigMap), not scattered across Task YAML
```

### 2. CLAUDE.md — Replace "Test-Driven Development" and "Behavior-Driven Development" subsections (lines ~33-46)

Replace both TDD and BDD subsections with a single concrete section:

```
### Testing and Validation

**What gets tested and how:**

| Artifact | Tool | When |
|----------|------|------|
| All YAML | `yamllint` | Every commit (tox, pre-commit) |
| Tekton Task/Pipeline YAML | `tekton-lint` | Every commit (tox) |
| Kustomize overlays | `kustomize build` + `kubeconform` | Every commit (tox) |
| Python CLI tools | `pytest` with 100% coverage | Every commit (tox) |
| Pipeline integration | Manual `tkn pipeline start` on hub | Per-phase acceptance |
| End-to-end lifecycle | Provision → post-provision → deprovision on test cluster | Phase 3+ |

**Test directory layout:**
```
tests/
├── conftest.py
├── unit/           # Python CLI tool tests (all tasks)
├── validation/     # kustomize build + kubeconform checks
└── data/           # fixtures (sample cluster dirs, expected outputs)
```

**Rules:**
- `tox` orchestrates all checks — `tox` must pass before any commit
- Validation tests for Kustomize overlays come before the YAML they validate
- Python CLI tools require pytest tests before implementation (TDD)
- Integration tests are run manually against a real hub cluster, not in CI initially
```

### 3. CLAUDE.md — Add new "Code Quality" subsection after "Testing and Validation"

```
### Code Quality

**Linting (all via `tox`):**
- `yamllint` — all YAML files
- `tekton-lint` — Tekton Task/Pipeline definitions
- `ansible-lint` — Ansible playbooks/roles (when Ansible is added)
- `black` + `mypy` + `pylint` + `bandit` — Python code (from Phase 1)

**Pre-commit hooks:**
- `gitleaks` — secret detection on every push

**`tox` is the single entry point** — never run linters individually in CI or commit workflows.
```

### 4. CLAUDE.md — Remove BDD subsection entirely (lines ~42-46)

The Given/When/Then format doesn't add value for infrastructure YAML. The acceptance criteria in the migration plan already serve this purpose. Remove the BDD subsection.

### 5. docs/plans/migration-plan.md — Add tooling files to Phase 1 scaffolding

Add these files to the Phase 1 "Files to create" tree (after the existing entries):

```
fleet/
├── .yamllint
├── .tektonlintrc.yaml
├── .pre-commit-config.yaml
├── pyproject.toml
├── tox.ini
├── Makefile
├── Dockerfile              # Pipeline container image (Python tools + oc CLI)
├── fleet/                  # Python package (CLI tools for Tekton tasks)
│   ├── __init__.py
│   └── tasks/
│       └── __init__.py
└── tests/
    ├── conftest.py
    ├── unit/
    │   └── __init__.py
    └── validation/
        └── test_kustomize_build.py
```

Then add content sections for each file after the existing Phase 1 content sections:

**`.yamllint`** — based on operator-pipelines:
- extends: default
- line-length max: 180
- ignore: .tox/, .venv/, tmp/

**`.tektonlintrc.yaml`**:
- paths: tekton/tasks/, tekton/pipelines/
- disable: prefer-kebab-case (match operator-pipelines convention)

**`.pre-commit-config.yaml`**:
- gitleaks v8.18.0

**`pyproject.toml`** (Poetry):
- Python >=3.11
- Runtime deps: pyyaml, kubernetes (for K8s API calls from Python CLI tools)
- Dev deps: pytest, pytest-cov, tox, yamllint, black, mypy, pylint, bandit
- Console script entry points for each Tekton task CLI tool (added as tasks are built)
- Package name: `fleet` (source in `fleet/` or `src/fleet/`)

**`tox.ini`**:
- Environments: test, yamllint, tekton-lint, validate-kustomize, black, mypy, pylint, bandit
- test: `pytest -v --cov fleet --cov-report term-missing --cov-fail-under 100`
- yamllint: `yamllint -c .yamllint .`
- tekton-lint: `tekton-lint tekton/` (or npm-based)
- validate-kustomize: `pytest tests/validation/`
- black, mypy, pylint, bandit: Python quality checks

**`Makefile`**:
- `make lint` — runs `tox` (all environments)
- `make lint-yaml` — runs `tox -e yamllint`
- `make lint-tekton` — runs `tox -e tekton-lint`
- `make validate` — runs `tox -e validate-kustomize`

**`tests/validation/test_kustomize_build.py`**:
- Discovers all `clusters/*/kustomization.yaml`
- Runs `kustomize build` on each
- Optionally pipes through `kubeconform` for schema validation
- Exits non-zero on any failure

### 6. docs/plans/migration-plan.md — Update Phase 1 acceptance criteria

Add to the existing acceptance criteria list:
- [ ] `tox` passes (yamllint, tekton-lint)
- [ ] pre-commit hooks installed and gitleaks runs on push
- [ ] `tests/` directory exists with validation scaffolding
- [ ] `make lint` works

### 7. docs/plans/migration-plan.md — Add note about Python CLI pattern for all task definitions

Add a note at the top of Phase 2 (where Tekton tasks are defined) explaining the pattern:
- Each Tekton task's `script:` field is a thin bash stub calling a Python CLI entry point
- Python source lives in `fleet/tasks/` and is tested via `tests/unit/`
- The migration plan's existing inline bash task bodies will be reimplemented as Python CLI tools
- The Tekton Task YAML structure (params, workspaces, results) stays the same — only the script content changes

This is a *note* in the migration plan, not a rewrite of all task YAML — the task YAML will be written correctly during implementation.

## Files to modify

1. `/home/mrhillsman/Development/misc/redhat-openshift-partner-labs/fleet/CLAUDE.md`
2. `/home/mrhillsman/Development/misc/redhat-openshift-partner-labs/fleet/docs/plans/migration-plan.md`

## Verification

After changes:
1. Read both files end-to-end and confirm no contradictions remain
2. Confirm every "write tests first" rule maps to a specific tool
3. Confirm Phase 1 file list includes all tooling config (pyproject.toml, tox.ini, Dockerfile, fleet/ package, tests/)
4. Confirm "Python for Tekton tasks" is consistent everywhere — CLAUDE.md, migration plan Phase 2+ task definitions
5. Confirm no remaining references to "inline bash" as the primary task scripting approach
