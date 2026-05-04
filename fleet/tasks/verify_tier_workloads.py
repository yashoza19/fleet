"""Verify tier-specific workloads are ready on the spoke cluster.

CLI: fleet-verify-tier-workloads --cluster-name NAME --tier TIER --spoke-kubeconfig PATH
Verifies CNV or AI workloads are ready: HyperConverged Available, operator deployments ready. Exits 1 on failure.
"""

import argparse
import json
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    tier = args.tier
    configure("verify-tier-workloads")

    info("=== Verifying tier-specific workloads on spoke cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  tier={tier}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    # Determine resources to check based on tier
    if tier == "virt":
        hc_namespace = "openshift-cnv"
        hc_resource = "hyperconverged/kubevirt-hyperconverged"
        # Check deployments in both NFD and CNV namespaces
        deployment_checks = [
            {"namespace": "openshift-nfd", "deployments": ["nfd-controller-manager"]},
            {"namespace": "openshift-cnv", "deployments": ["virt-operator", "cdi-operator"]},
        ]
    elif tier == "ai":
        hc_namespace = "openshift-ai"
        hc_resource = "aicluster/ai-cluster"  # Hypothetical for AI tier
        deployment_checks = [
            {"namespace": "openshift-ai", "deployments": ["ai-operator", "gpu-operator"]},
        ]
    else:
        error(f"Unsupported tier: {tier}")
        sys.exit(1)

    # Phase 1: Wait for HyperConverged (or equivalent) to be Available
    info(f"Phase 1: Waiting for {hc_resource} to be Available...")

    wait_result = subprocess.run(
        [
            "oc", "wait",
            "--for=condition=Available",
            hc_resource,
            "-n", hc_namespace,
            f"--kubeconfig={args.spoke_kubeconfig}",
            "--timeout=15m"
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc wait exit code: {wait_result.returncode}")
    if wait_result.returncode != 0:
        error(f"HyperConverged not available: {wait_result.stderr}")
        sys.exit(1)
    info(f"  -> {hc_resource} is Available")

    # Phase 2: Verify operator deployments are ready across all namespaces
    info(f"Phase 2: Verifying operator deployments...")

    all_deployments = []
    for check in deployment_checks:
        namespace = check["namespace"]
        deployments = check["deployments"]

        info(f"  Checking deployments in {namespace}...")

        for deployment in deployments:
            info(f"    Checking deployment {deployment}...")

            status_result = subprocess.run(
                [
                    "oc", "get",
                    f"deployment/{deployment}",
                    "-n", namespace,
                    f"--kubeconfig={args.spoke_kubeconfig}",
                    "-o", "json"
                ],
                capture_output=True,
                text=True,
            )
            info(f"      -> oc get exit code: {status_result.returncode}")
            if status_result.returncode != 0:
                error(f"Failed to get deployment {deployment}: {status_result.stderr}")
                sys.exit(1)

            try:
                deploy_data = json.loads(status_result.stdout)
                status = deploy_data.get("status", {})
                ready_replicas = status.get("readyReplicas", 0)
                total_replicas = status.get("replicas", 0)

                info(f"      -> Replicas: {ready_replicas}/{total_replicas}")

                if ready_replicas != total_replicas:
                    error(f"Deployment {deployment} not ready: {ready_replicas}/{total_replicas} replicas ready")
                    sys.exit(1)

                info(f"      -> Deployment {deployment} is ready")
                all_deployments.append(f"{namespace}/{deployment}")

            except (json.JSONDecodeError, KeyError) as e:
                error(f"Failed to parse deployment status for {deployment}: {e}")
                sys.exit(1)

    # Phase 3: Log verification summary
    info("Phase 3: Verification summary")
    info(f"  ✓ {hc_resource} is Available")
    for deployment in all_deployments:
        info(f"  ✓ {deployment} deployment is ready")

    info(f"Tier {tier} workloads verified successfully")