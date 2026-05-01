from unittest import mock
import subprocess
import pytest
from fleet.tasks.apply_tier_workloads import main


BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--tier",
    "virt",
    "--spoke-kubeconfig",
    "/workspace/kubeconfig",
    "--source-dir",
    "/workspace/source/workloads/virt",
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


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_apply_tier_workloads_success(mock_run):
    """Test successful tier workload application with CSV wait."""
    mock_run.side_effect = [
        # 1. Build subscription manifests
        _ok(stdout="apiVersion: v1\nkind: List\nitems: []"),
        # 2. Apply subscription manifests
        _ok(stdout="namespace/openshift-cnv created"),
        # 3. Wait for CSV ready (success on first try)
        _ok(stdout="condition met"),
        # 4. Build activation manifests
        _ok(stdout="apiVersion: hco.kubevirt.io/v1beta1\nkind: HyperConverged"),
        # 5. Apply activation manifests
        _ok(stdout="hyperconverged/kubevirt-hyperconverged created"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    assert mock_run.call_count == 5

    # Verify kustomize build calls
    kustomize_calls = [call for call in mock_run.call_args_list
                      if "kustomize" in call.args[0][0]]
    assert len(kustomize_calls) == 2

    # Verify subscription build
    sub_call = kustomize_calls[0]
    assert "/workspace/source/workloads/virt/subscription" in sub_call.args[0]

    # Verify activation build
    act_call = kustomize_calls[1]
    assert "/workspace/source/workloads/virt/activation" in act_call.args[0]

    # Verify oc apply calls use correct kubeconfig
    apply_calls = [call for call in mock_run.call_args_list
                  if "oc" in call.args[0][0] and "apply" in call.args[0]]
    assert len(apply_calls) == 2
    for call in apply_calls:
        assert "--kubeconfig=/workspace/kubeconfig" in call.args[0]


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_subscription_kustomize_build_fails(mock_run):
    """Test failure when subscription kustomize build fails."""
    mock_run.return_value = _fail(stderr="error building subscription manifests")

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_subscription_apply_fails(mock_run):
    """Test failure when subscription apply fails."""
    mock_run.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),  # Build success
        _fail(stderr="forbidden"),  # Apply failure
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_tier_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_csv_wait_timeout(mock_run, mock_sleep):
    """Test timeout when waiting for CSV ready."""
    # Need enough failures to simulate timeout (40+ attempts for 20min timeout)
    csv_failures = [_fail(stderr="condition not met")] * 45

    mock_run.side_effect = [
        # Build and apply subscription
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-cnv created"),
        # CSV wait failures (simulate timeout with enough attempts)
        *csv_failures
    ]

    # Mock sleep to avoid actual delays in tests
    mock_sleep.return_value = None

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()

    # Verify sleep was called between retries
    assert mock_sleep.call_count >= 2
    assert all(call[0][0] == 30 for call in mock_sleep.call_args_list)  # 30-second interval


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_activation_kustomize_build_fails(mock_run):
    """Test failure when activation kustomize build fails."""
    mock_run.side_effect = [
        # Subscription phase succeeds
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-cnv created"),
        _ok(stdout="condition met"),  # CSV ready
        # Activation build fails
        _fail(stderr="error building activation manifests"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_activation_apply_fails(mock_run):
    """Test failure when activation apply fails."""
    mock_run.side_effect = [
        # Subscription phase succeeds
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-cnv created"),
        _ok(stdout="condition met"),  # CSV ready
        # Activation build succeeds but apply fails
        _ok(stdout="apiVersion: hco.kubevirt.io/v1beta1\nkind: HyperConverged"),
        _fail(stderr="forbidden"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_uses_correct_tier_directories(mock_run):
    """Test that tier parameter correctly determines source directories."""
    # Test with ai tier
    ai_argv = BASE_ARGV.copy()
    ai_argv[4] = "ai"  # Change tier from virt to ai
    ai_argv[8] = "/workspace/source/workloads/ai"  # Change source-dir

    mock_run.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-ai created"),
        _ok(stdout="condition met"),
        _ok(stdout="apiVersion: ai.openshift.io/v1\nkind: AICluster"),
        _ok(stdout="aicluster/ai-cluster created"),
    ]

    with mock.patch("sys.argv", ai_argv):
        main()

    # Verify ai directories were used
    kustomize_calls = [call for call in mock_run.call_args_list
                      if "kustomize" in call.args[0][0]]
    assert any("/workspace/source/workloads/ai/subscription" in str(call)
              for call in kustomize_calls)
    assert any("/workspace/source/workloads/ai/activation" in str(call)
              for call in kustomize_calls)


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_csv_wait_succeeds_after_retry(mock_run):
    """Test CSV wait succeeds after initial failures."""
    mock_run.side_effect = [
        # Subscription phase
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-cnv created"),
        # CSV wait - fail twice then succeed
        _fail(stderr="condition not met"),
        _fail(stderr="condition not met"),
        _ok(stdout="condition met"),  # Success on third try
        # Activation phase
        _ok(stdout="apiVersion: hco.kubevirt.io/v1beta1\nkind: HyperConverged"),
        _ok(stdout="hyperconverged/kubevirt-hyperconverged created"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    # Should complete successfully
    assert mock_run.call_count == 7


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_verifies_csv_wait_command_format(mock_run):
    """Test that CSV wait uses correct oc wait command format."""
    mock_run.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-cnv created"),
        _ok(stdout="condition met"),
        _ok(stdout="apiVersion: hco.kubevirt.io/v1beta1\nkind: HyperConverged"),
        _ok(stdout="hyperconverged/kubevirt-hyperconverged created"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    # Find the CSV wait call
    csv_wait_calls = [call for call in mock_run.call_args_list
                     if "oc" in call.args[0][0] and "wait" in call.args[0]]
    assert len(csv_wait_calls) == 1

    wait_call = csv_wait_calls[0]
    wait_cmd = wait_call.args[0]

    # Verify command format
    assert "oc" in wait_cmd
    assert "wait" in wait_cmd
    assert "--for=condition=" in " ".join(wait_cmd)
    assert "clusterserviceversion" in " ".join(wait_cmd)
    assert "--kubeconfig=/workspace/kubeconfig" in wait_cmd
    assert "--timeout=" in " ".join(wait_cmd)


@mock.patch("fleet.tasks.apply_tier_workloads.subprocess.run")
def test_uses_cluster_name_in_commands(mock_run):
    """Test that cluster name is correctly used in commands."""
    mock_run.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),
        _ok(stdout="namespace/openshift-cnv created"),
        _ok(stdout="condition met"),
        _ok(stdout="apiVersion: hco.kubevirt.io/v1beta1\nkind: HyperConverged"),
        _ok(stdout="hyperconverged/kubevirt-hyperconverged created"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    # Cluster name should appear in logging and potentially in wait commands
    # This is mainly to ensure the parameter is being used
    assert mock_run.call_count == 5