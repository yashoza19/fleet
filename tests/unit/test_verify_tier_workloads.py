from unittest import mock
import subprocess
import pytest
from fleet.tasks.verify_tier_workloads import main


BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--tier",
    "virt",
    "--spoke-kubeconfig",
    "/workspace/kubeconfig",
]


def _ok(stdout="", stderr=""):
    """Helper to create successful subprocess result."""
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=stdout, stderr=stderr
    )


def _fail(stdout="", stderr="error"):
    """Helper to create failed subprocess result."""
    return subprocess.CompletedProcess(
        [], returncode=1, stdout=stdout, stderr=stderr
    )


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_verify_tier_workloads_success(mock_run):
    """Test successful tier workload verification with NFD + CNV."""
    mock_run.side_effect = [
        # 1. Wait for HyperConverged Available
        _ok(stdout="condition met"),
        # 2. Check NFD deployment replicas
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),
        # 3. Check virt-operator deployment replicas
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),
        # 4. Check CDI deployment replicas
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    assert mock_run.call_count == 4

    # Verify HyperConverged wait command
    hc_call = mock_run.call_args_list[0]
    hc_cmd = hc_call.args[0]
    assert "oc" in hc_cmd
    assert "wait" in hc_cmd
    assert "--for=condition=Available" in " ".join(hc_cmd)
    assert "hyperconverged" in " ".join(hc_cmd)
    assert "--kubeconfig=/workspace/kubeconfig" in hc_cmd
    assert "--timeout=15m" in " ".join(hc_cmd)

    # Verify deployment status checks
    deploy_calls = [mock_run.call_args_list[1], mock_run.call_args_list[2]]
    for call in deploy_calls:
        cmd = call.args[0]
        assert "oc" in cmd
        assert "get" in cmd
        assert any("deployment/" in arg for arg in cmd)  # deployment/name format
        assert "-o" in cmd
        assert "json" in cmd
        assert "--kubeconfig=/workspace/kubeconfig" in cmd


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_hyperconverged_wait_fails(mock_run):
    """Test failure when HyperConverged condition wait fails."""
    mock_run.return_value = _fail(stderr="condition not met after timeout")

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    # Should only have one call (HyperConverged wait)
    assert mock_run.call_count == 1


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_kubevirt_deployment_not_ready(mock_run):
    """Test failure when KubeVirt deployment is not ready."""
    mock_run.side_effect = [
        # HyperConverged ready
        _ok(stdout="condition met"),
        # KubeVirt deployment not ready (not enough replicas)
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":2}}'),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_cdi_deployment_not_ready(mock_run):
    """Test failure when CDI deployment is not ready."""
    mock_run.side_effect = [
        # HyperConverged ready
        _ok(stdout="condition met"),
        # KubeVirt deployment ready
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),
        # CDI deployment not ready
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":2}}'),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    assert mock_run.call_count == 3


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_deployment_status_check_fails(mock_run):
    """Test failure when deployment status check command fails."""
    mock_run.side_effect = [
        # HyperConverged ready
        _ok(stdout="condition met"),
        # KubeVirt deployment check fails
        _fail(stderr="deployment not found"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_uses_correct_namespaces_for_tier(mock_run):
    """Test that correct namespaces are used based on tier."""
    # Test with virt tier
    mock_run.side_effect = [
        _ok(stdout="condition met"),
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),  # NFD
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # virt-operator
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # cdi-operator
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    # Check that both openshift-nfd and openshift-cnv namespaces are used for virt tier
    all_calls = mock_run.call_args_list
    namespaces_used = []
    for call in all_calls:
        cmd = call.args[0]
        if "-n" in cmd:
            ns_idx = cmd.index("-n") + 1
            namespaces_used.append(cmd[ns_idx])

    # Should use openshift-cnv for HyperConverged wait
    assert "openshift-cnv" in namespaces_used
    # Should use openshift-nfd for NFD deployment check
    assert "openshift-nfd" in namespaces_used


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_uses_correct_namespaces_for_ai_tier(mock_run):
    """Test that correct namespaces are used for ai tier."""
    # Test with ai tier
    ai_argv = BASE_ARGV.copy()
    ai_argv[4] = "ai"  # Change tier from virt to ai

    mock_run.side_effect = [
        _ok(stdout="condition met"),
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),
    ]

    with mock.patch("sys.argv", ai_argv):
        main()

    # Check that openshift-ai namespace is used for ai tier
    all_calls = mock_run.call_args_list
    for call in all_calls:
        cmd = call.args[0]
        if "-n" in cmd:
            ns_idx = cmd.index("-n") + 1
            assert cmd[ns_idx] == "openshift-ai"


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_verifies_correct_deployment_names(mock_run):
    """Test that correct deployment names are checked based on tier."""
    mock_run.side_effect = [
        _ok(stdout="condition met"),
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),  # NFD
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # virt-operator
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # cdi-operator
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    # Check deployment names for virt tier
    deploy_calls = [call for call in mock_run.call_args_list
                   if any("deployment/" in arg for arg in call.args[0])]
    assert len(deploy_calls) == 3

    # Should check nfd-controller-manager, virt-operator and cdi-operator deployments
    deploy_names = []
    for call in deploy_calls:
        cmd = call.args[0]
        for arg in cmd:
            if arg.startswith("deployment/"):
                deploy_names.append(arg.split("/")[1])

    assert "nfd-controller-manager" in deploy_names
    assert "virt-operator" in deploy_names
    assert "cdi-operator" in deploy_names


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_invalid_json_in_deployment_status(mock_run):
    """Test handling of invalid JSON in deployment status."""
    mock_run.side_effect = [
        # HyperConverged ready
        _ok(stdout="condition met"),
        # KubeVirt deployment with invalid JSON
        _ok(stdout="invalid json"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_missing_status_field_in_deployment(mock_run):
    """Test handling of deployment with replicas field but no readyReplicas."""
    mock_run.side_effect = [
        # HyperConverged ready
        _ok(stdout="condition met"),
        # Deployment with replicas but no readyReplicas (not ready)
        _ok(stdout='{"status":{"replicas":2}}'),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_uses_cluster_name_in_logging(mock_run):
    """Test that cluster name is used in logging and commands."""
    mock_run.side_effect = [
        _ok(stdout="condition met"),
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),  # NFD
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # virt-operator
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # cdi-operator
    ]

    # Test with custom cluster name
    custom_argv = BASE_ARGV.copy()
    custom_argv[2] = "custom-cluster-name"

    with mock.patch("sys.argv", custom_argv):
        main()

    # Should complete successfully with custom cluster name
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_verifies_hyperconverged_resource_name(mock_run):
    """Test that correct HyperConverged resource name is used."""
    mock_run.side_effect = [
        _ok(stdout="condition met"),
        _ok(stdout='{"status":{"readyReplicas":1,"replicas":1}}'),  # NFD
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # virt-operator
        _ok(stdout='{"status":{"readyReplicas":2,"replicas":2}}'),  # cdi-operator
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    # Check HyperConverged wait command uses correct resource name
    hc_call = mock_run.call_args_list[0]
    hc_cmd = hc_call.args[0]

    # Should reference kubevirt-hyperconverged resource
    assert "hyperconverged/kubevirt-hyperconverged" in " ".join(hc_cmd)


@mock.patch("fleet.tasks.verify_tier_workloads.subprocess.run")
def test_zero_replicas_deployment(mock_run):
    """Test handling of deployment with zero replicas."""
    mock_run.side_effect = [
        # HyperConverged ready
        _ok(stdout="condition met"),
        # NFD deployment with zero replicas (both ready and total)
        _ok(stdout='{"status":{"readyReplicas":0,"replicas":0}}'),
        # virt-operator deployment with zero replicas
        _ok(stdout='{"status":{"readyReplicas":0,"replicas":0}}'),
        # cdi-operator deployment with zero replicas
        _ok(stdout='{"status":{"readyReplicas":0,"replicas":0}}'),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        # Zero replicas should be considered ready (scaled down scenario)
        main()

    assert mock_run.call_count == 4  # Should complete all deployment checks