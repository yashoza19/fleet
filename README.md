# fleet

> **Status:** 🚧 Early development. Architecture agreed; implementation in progress.

OpenShift cluster fleet management for Red Hat OpenShift Partner Labs. Hub-and-spoke provisioning, post-provisioning configuration, and day-2 operations for OpenShift clusters delivered to third-party partners.

## What lives here

This repo is the **control plane** for our OpenShift fleet. It holds the declarative definitions (cluster specs, tier configs, pipeline definitions) and is the trigger surface for cluster lifecycle operations.

It does **not** hold: day-2 workloads, tenant application manifests, or anything that runs on the spoke clusters long-term. Those belong in sibling repos.

## Architecture at a glance

- **Git** (this repo) — source of truth for cluster definitions and pipelines
- **Tekton** (OpenShift Pipelines) — workflow engine for provision, post-provision, and deprovision
- **ArgoCD** (OpenShift GitOps) — manifest delivery to the hub + day-2 workload delivery to spokes via `ApplicationSet`
- **ACM + Hive** — fleet membership and cluster provisioning
- **cert-manager + Vault** — hub-side secret authority; spokes receive only derived artifacts

The guiding rule: *ArgoCD reconciles declarative state. Tekton runs ordered workflows. ACM/Hive controls cluster lifecycle.* Each tool does one job.

## Repo layout (planned)

```
.
├── bootstrap/          # Hub bootstrap (ArgoCD, Tekton install, ACM config)
├── tekton/             # Pipeline, Task, EventListener, Trigger definitions
├── clusters/           # One directory per cluster (spec, tier label, overrides)
├── hub-config/         # cert-manager, Vault/ESO, baseline hub operators
├── workloads/          # Tier-specific day-2 overlays (base / virt / ai)
└── docs/               # Architecture, runbooks, diagrams
```

## Status

| Area | State |
|---|---|
| Architecture direction | ✅ Agreed |
| Repo structure | ⏳ Planned |
| Hub bootstrap (Tekton, cert-manager) | ⏳ Planned |
| Provision pipeline | ⏳ Planned |
| Post-provision pipeline (base tier) | ⏳ Planned |
| Post-provision pipeline (virt, ai tiers) | ⏳ Planned |
| Deprovision pipeline | ⏳ Planned |
| ApplicationSet day-2 delivery | ⏳ Planned |
| Migration from `labargocd` | ⏳ Planned |

## Background

This repo supersedes the cluster-lifecycle portions of [`labargocd`](https://github.com/redhat-openshift-partner-labs/labargocd). Architecture rationale and migration plan are in [`docs/architecture.md`](./docs/architecture.md).

## Contributing

Not open for contributions yet. Issues and discussion welcome as scaffolding lands.
