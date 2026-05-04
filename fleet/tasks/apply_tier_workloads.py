"""Apply tier-specific workloads to the spoke cluster.

CLI: fleet-apply-tier-workloads --cluster-name NAME --tier TIER --spoke-kubeconfig PATH --source-dir DIR
Applies CNV or AI workloads in phases: subscription -> CSV wait -> activation. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import time

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    tier = args.tier
    configure("apply-tier-workloads")

    info("=== Applying tier-specific workloads to spoke cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  tier={tier}")
    info(f"  source-dir={args.source_dir}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    # Phase 1: Build and apply subscription manifests
    subscription_dir = f"{args.source_dir}/subscription"
    info(f"Phase 1: Building subscription manifests from {subscription_dir}...")

    build = subprocess.run(
        ["kustomize", "build", subscription_dir],
        capture_output=True,
        text=True,
    )
    info(f"  -> kustomize build exit code: {build.returncode}")
    if build.returncode != 0:
        error(f"kustomize build stderr: {build.stderr}")
        sys.exit(1)

    doc_count = len([l for l in build.stdout.split("---") if l.strip()])
    info(f"  -> kustomize produced {doc_count} subscription YAML documents")

    info(f"Applying subscription manifests to spoke...")
    apply = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"oc apply stderr: {apply.stderr}")
        sys.exit(1)
    info(f"  -> Apply output: {apply.stdout.strip()}")

    # Phase 2: Wait for operator CSVs to be ready
    info("Phase 2: Waiting for operator CSVs to be ready...")
    csv_timeout = 1200  # 20 minutes in seconds
    csv_interval = 30  # 30-second polling interval
    csv_elapsed = 0

    # Define namespaces to check based on tier
    if tier == "virt":
        namespaces_to_check = ["openshift-nfd", "openshift-cnv"]
        operator_names = ["NFD", "CNV"]
    elif tier == "ai":
        namespaces_to_check = [f"openshift-{tier}"]
        operator_names = ["AI"]
    else:
        namespaces_to_check = [f"openshift-{tier}"]
        operator_names = [tier.upper()]

    # Wait for CSVs in all required namespaces
    all_csvs_ready = False
    while csv_elapsed < csv_timeout:
        info(f"  Checking operator CSVs [{csv_elapsed}s/{csv_timeout}s]...")

        ready_count = 0
        for i, namespace in enumerate(namespaces_to_check):
            info(f"    Checking {operator_names[i]} CSV in {namespace}...")

            wait_result = subprocess.run(
                [
                    "oc", "wait",
                    "--for=condition=Succeeded",
                    "clusterserviceversion",
                    "--all",
                    "-n", namespace,
                    f"--kubeconfig={args.spoke_kubeconfig}",
                    "--timeout=30s"
                ],
                capture_output=True,
                text=True,
            )

            if wait_result.returncode == 0:
                info(f"    -> {operator_names[i]} CSV is ready")
                ready_count += 1
            else:
                info(f"    -> {operator_names[i]} CSV not ready yet")

        if ready_count == len(namespaces_to_check):
            info(f"  -> All operator CSVs are ready!")
            all_csvs_ready = True
            break

        csv_elapsed += csv_interval
        if csv_elapsed < csv_timeout:
            info(f"  -> Waiting {csv_interval}s for remaining CSVs...")
            time.sleep(csv_interval)

    if not all_csvs_ready:
        error(f"Not all operator CSVs ready after {csv_timeout}s timeout")
        sys.exit(1)

    # Phase 3: Build and apply activation manifests
    activation_dir = f"{args.source_dir}/activation"
    info(f"Phase 3: Building activation manifests from {activation_dir}...")

    build = subprocess.run(
        ["kustomize", "build", activation_dir],
        capture_output=True,
        text=True,
    )
    info(f"  -> kustomize build exit code: {build.returncode}")
    if build.returncode != 0:
        error(f"kustomize build stderr: {build.stderr}")
        sys.exit(1)

    doc_count = len([l for l in build.stdout.split("---") if l.strip()])
    info(f"  -> kustomize produced {doc_count} activation YAML documents")

    info(f"Applying activation manifests to spoke...")
    apply = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"oc apply stderr: {apply.stderr}")
        sys.exit(1)
    info(f"  -> Apply output: {apply.stdout.strip()}")

    info(f"Tier {tier} workloads applied successfully")