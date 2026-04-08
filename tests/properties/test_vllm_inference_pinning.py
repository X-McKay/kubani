"""Property-based tests for vLLM inference node pinning and GPU memory budget.

Feature: cluster-stability, Property 5: All vLLM deployments are pinned to the inference node
Feature: cluster-stability, Property 6: Combined vLLM GPU memory utilization does not exceed 85%
Validates: Requirements 7.1, 7.2
"""

from pathlib import Path

import yaml

VLLM_DIR = Path("infrastructure/gitops/apps/vllm")

VLLM_DEPLOYMENT_FILES = [
    VLLM_DIR / "deployment.yaml",
    VLLM_DIR / "fast-model-deployment.yaml",
    VLLM_DIR / "embeddings-deployment.yaml",
]

MODEL_CONFIG_PATH = VLLM_DIR / "model-config.yaml"

# The topology label that pins workloads to the inference node (sparky)
EXPECTED_INFERENCE_LABEL = "topology.kubani.io/usage-class"
EXPECTED_INFERENCE_VALUE = "inference"

# GPU memory budget cap (Property 6)
GPU_MEMORY_UTILIZATION_CAP = 0.85

# Keys in the ConfigMap data section
GPU_UTILIZATION_KEYS = [
    "LLM_GPU_MEMORY_UTILIZATION",
    "FAST_GPU_MEMORY_UTILIZATION",
    "EMBEDDINGS_GPU_MEMORY_UTILIZATION",
]


def load_yaml(path: Path) -> dict:
    assert path.exists(), f"Required manifest not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


def get_node_selector(deployment: dict) -> dict:
    """Extract spec.template.spec.nodeSelector from a Deployment manifest."""
    return (
        deployment.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("nodeSelector", {})
    )


# --- Property 5: vLLM inference node pinning ---


def test_property_5_all_vllm_deployment_files_exist():
    """All three vLLM deployment files must be present."""
    for path in VLLM_DEPLOYMENT_FILES:
        assert path.exists(), f"vLLM deployment manifest not found: {path}"


def test_property_5_all_vllm_deployments_pinned_to_inference_node():
    """
    Feature: cluster-stability, Property 5: All vLLM deployments are pinned to the inference node

    For any vLLM deployment (vllm, vllm-fast, vllm-embeddings), the pod spec must
    contain a nodeSelector that targets topology.kubani.io/usage-class: inference.
    This ensures all inference workloads land on sparky (the only inference-class node)
    without relying on a hostname-specific selector.

    Validates: Requirements 7.1
    """
    failures = []
    for path in VLLM_DEPLOYMENT_FILES:
        deployment = load_yaml(path)
        node_selector = get_node_selector(deployment)

        if EXPECTED_INFERENCE_LABEL not in node_selector:
            failures.append(
                f"{path.name}: nodeSelector missing key '{EXPECTED_INFERENCE_LABEL}'. "
                f"Got: {node_selector}"
            )
        elif node_selector[EXPECTED_INFERENCE_LABEL] != EXPECTED_INFERENCE_VALUE:
            failures.append(
                f"{path.name}: nodeSelector['{EXPECTED_INFERENCE_LABEL}'] = "
                f"'{node_selector[EXPECTED_INFERENCE_LABEL]}' (expected '{EXPECTED_INFERENCE_VALUE}')"
            )

    assert not failures, (
        "The following vLLM deployments are not pinned to the inference node:\n"
        + "\n".join(f"  - {f}" for f in failures)
        + f"\nEach deployment must have nodeSelector: {{{EXPECTED_INFERENCE_LABEL}: {EXPECTED_INFERENCE_VALUE}}}"
    )


def test_property_5_vllm_deployments_do_not_use_hostname_selector():
    """
    vLLM deployments must not use kubernetes.io/hostname for node pinning.
    Topology labels should be used instead for maintainability.

    Validates: Requirements 7.1
    """
    failures = []
    for path in VLLM_DEPLOYMENT_FILES:
        deployment = load_yaml(path)
        node_selector = get_node_selector(deployment)
        if "kubernetes.io/hostname" in node_selector:
            failures.append(
                f"{path.name}: still uses kubernetes.io/hostname={node_selector['kubernetes.io/hostname']!r}. "
                "Replace with topology.kubani.io/usage-class: inference"
            )

    assert not failures, (
        "The following vLLM deployments still use hostname-based node selectors:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


# --- Property 6: GPU memory budget ---


def test_property_6_model_config_exists():
    """The vLLM model-config ConfigMap must exist."""
    assert MODEL_CONFIG_PATH.exists(), f"model-config.yaml not found at {MODEL_CONFIG_PATH}"


def test_property_6_combined_gpu_memory_utilization_within_budget():
    """
    Feature: cluster-stability, Property 6: Combined vLLM GPU memory utilization does not exceed 85%

    For any combination of GPU memory utilization values across the three vLLM deployments
    (read from model-config.yaml), their sum must be less than or equal to 0.85.

    Validates: Requirements 7.2
    """
    config = load_yaml(MODEL_CONFIG_PATH)
    data = config.get("data", {})

    missing = [k for k in GPU_UTILIZATION_KEYS if k not in data]
    assert not missing, (
        f"model-config.yaml is missing GPU utilization keys: {missing}"
    )

    utilization_values = {}
    for key in GPU_UTILIZATION_KEYS:
        try:
            utilization_values[key] = float(data[key])
        except (ValueError, TypeError) as e:
            raise AssertionError(
                f"model-config.yaml key '{key}' has non-numeric value: {data[key]!r}"
            ) from e

    total = sum(utilization_values.values())

    assert total <= GPU_MEMORY_UTILIZATION_CAP, (
        f"Combined GPU memory utilization {total:.2%} exceeds the {GPU_MEMORY_UTILIZATION_CAP:.0%} cap.\n"
        + "\n".join(f"  {k}: {v:.0%}" for k, v in utilization_values.items())
        + f"\n  Total: {total:.0%} (limit: {GPU_MEMORY_UTILIZATION_CAP:.0%})"
    )


def test_property_6_individual_gpu_utilization_values_are_valid():
    """
    Each individual GPU memory utilization value must be between 0 and 1 (exclusive).

    Validates: Requirements 7.2
    """
    config = load_yaml(MODEL_CONFIG_PATH)
    data = config.get("data", {})

    failures = []
    for key in GPU_UTILIZATION_KEYS:
        if key not in data:
            failures.append(f"{key}: missing")
            continue
        try:
            val = float(data[key])
        except (ValueError, TypeError):
            failures.append(f"{key}: non-numeric value {data[key]!r}")
            continue
        if not (0 < val < 1):
            failures.append(f"{key}: {val} is not in range (0, 1)")

    assert not failures, (
        "Invalid GPU utilization values in model-config.yaml:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )
