"""Core helpers for StarBridge MCP.

Exposes the safety layer: evidence manifests, job status, security redaction,
safe roots, tool registry, result schemas, and computer-use adapters.
"""

__all__ = [
    # Evidence & results
    "DEFAULT_EVIDENCE_ROOT",
    "DEFAULT_MANIFEST_FILENAME",
    "EvidenceManifest",
    "EvidenceItem",
    "ExecutionResult",
    "ValidationResult",
    "create_manifest",
    "save_manifest",
    "load_manifest",
    "ensure_evidence_path",
    "repo_relative",
    # Job & status
    "JobStatus",
    "CreativeTransaction",
    "ModelPolicy",
    "create_recipe_transaction",
    "build_operation_context",
    "operation_context_contract",
    "build_queue_snapshot",
    "normalize_queue_payload",
    "queue_snapshot_contract",
    "VectorDimensionResult",
    "VectorQualityFinding",
    "evaluate_reference_vector_quality",
    "validate_reference_vector_quality_report",
    "default_vector_task",
    "parse_vector_command",
    "validate_vector_task",
    "compile_vector_scene_to_svg",
    "validate_vector_scene",
    "vector_scene_summary",
    # Security & safety
    "sanitize",
    "sanitize_path",
    "redact_path",
    "redact_text",
    "safe_roots_summary",
    # Registry & schemas
    "ToolCapability",
    "CAPABILITIES",
    "capability_summary",
    "list_capabilities",
    "BRIDGE_PROFILES",
    "BRIDGE_NAME_MAP",
    "BRIDGE_ALIASES",
    "make_result",
    "validate_result",
    # Config
    "StarBridgeConfig",
    "env_summary",
    # Computer use
    "ActionPlan",
    "CodexComputerUseAdapter",
    "evaluate_safety",
    "BaseBridge",
]

from starbridge_mcp.core.bridge_base import BaseBridge
from starbridge_mcp.core.computer_use import (
    ActionPlan,
    CodexComputerUseAdapter,
    evaluate_safety,
)
from starbridge_mcp.core.config import StarBridgeConfig, env_summary
from starbridge_mcp.core.evidence import (
    DEFAULT_EVIDENCE_ROOT,
    DEFAULT_MANIFEST_FILENAME,
    EvidenceItem,
    EvidenceManifest,
    ExecutionResult,
    ValidationResult,
    create_manifest,
    ensure_evidence_path,
    load_manifest,
    repo_relative,
    save_manifest,
)
from starbridge_mcp.core.job_status import JobStatus
from starbridge_mcp.core.operation_context import (
    build_operation_context,
    operation_context_contract,
)
from starbridge_mcp.core.queue_snapshot import (
    build_queue_snapshot,
    normalize_queue_payload,
    queue_snapshot_contract,
)
from starbridge_mcp.core.result_schema import make_result, validate_result
from starbridge_mcp.core.safe_roots import safe_roots_summary
from starbridge_mcp.core.security import redact_path, redact_text, sanitize, sanitize_path
from starbridge_mcp.core.tool_registry import (
    BRIDGE_ALIASES,
    BRIDGE_NAME_MAP,
    BRIDGE_PROFILES,
    CAPABILITIES,
    ToolCapability,
    capability_summary,
    list_capabilities,
)
from starbridge_mcp.core.transaction import (
    CreativeTransaction,
    ModelPolicy,
    create_recipe_transaction,
)
from starbridge_mcp.core.vector_intent import (
    default_vector_task,
    parse_vector_command,
    validate_vector_task,
)
from starbridge_mcp.core.vector_quality import (
    VectorDimensionResult,
    VectorQualityFinding,
    evaluate_reference_vector_quality,
    validate_reference_vector_quality_report,
)
from starbridge_mcp.core.vector_scene import (
    compile_vector_scene_to_svg,
    validate_vector_scene,
    vector_scene_summary,
)
