from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starbridge_mcp.core.security import sanitize


@dataclass(frozen=True)
class ToolCapability:
    name: str
    bridge: str
    action: str
    maturity: str
    risk_level: str
    description: str
    side_effects: str
    safe_default: bool
    requires_confirmation: bool
    requires_local_software: bool
    source_projects: tuple[str, ...] = field(default_factory=tuple)
    invocation: str | None = None
    next_step: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bridge": self.bridge,
            "action": self.action,
            "maturity": self.maturity,
            "risk_level": self.risk_level,
            "description": self.description,
            "side_effects": self.side_effects,
            "safe_default": self.safe_default,
            "requires_confirmation": self.requires_confirmation,
            "requires_local_software": self.requires_local_software,
            "source_projects": list(self.source_projects),
            "invocation": self.invocation,
            "next_step": self.next_step,
        }


CAPABILITIES: tuple[ToolCapability, ...] = (
    ToolCapability(
        name="starbridge.status",
        bridge="all",
        action="status",
        maturity="implemented",
        risk_level="safe_read_only",
        description="返回所有本地创意软件 bridge 的统一状态摘要。",
        side_effects="只读取环境变量和本机服务状态；不会打开用户文件。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("GLips/Figma-Context-MCP", "IO-AtelierTech/comfyui-mcp"),
        invocation="python -m starbridge_mcp.server status --json",
    ),
    ToolCapability(
        name="starbridge.tools",
        bridge="all",
        action="tools",
        maturity="implemented",
        risk_level="safe_read_only",
        description="列出 StarBridge 当前可用、实验中和计划中的安全工具能力。",
        side_effects="只返回静态能力清单。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("artokun/comfyui-mcp", "ie3jp/illustrator-mcp-server"),
        invocation="python -m starbridge_mcp.server tools --json",
    ),
    ToolCapability(
        name="autocad_dxf.status",
        bridge="autocad_dxf",
        action="status",
        maturity="implemented",
        risk_level="safe_read_only",
        description="检查离线 DXF bridge 是否能做 CAD plan 校验和 dry-run。",
        side_effects="不需要 AutoCAD，不打开 DWG/DXF。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("puran-water/autocad-mcp",),
        invocation="python examples/cad/generate_dxf_plan.py --dry-run",
    ),
    ToolCapability(
        name="autocad_dxf.validate_cad_plan",
        bridge="autocad_dxf",
        action="validate_cad_plan",
        maturity="implemented",
        risk_level="safe_read_only",
        description="校验 CAD JSON plan 的单位、图层和实体结构。",
        side_effects="只处理传入 JSON，不写文件。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("puran-water/autocad-mcp", "AnCode666/multiCAD-mcp"),
    ),
    ToolCapability(
        name="autocad_dxf.write_dxf",
        bridge="autocad_dxf",
        action="write_dxf",
        maturity="implemented",
        risk_level="guarded_local_write",
        description="把已校验 CAD plan 写成测试 DXF；默认应该先 dry-run。",
        side_effects="dry_run=False 时只允许写入 examples/cad/output。",
        safe_default=False,
        requires_confirmation=True,
        requires_local_software=False,
        source_projects=("puran-water/autocad-mcp",),
        next_step="保持真实 AutoCAD COM/MCP 控制与离线 DXF export 分离。",
    ),
    ToolCapability(
        name="comfyui.system_probe",
        bridge="comfyui",
        action="probe",
        maturity="implemented",
        risk_level="safe_read_only",
        description="读取 ComfyUI /system_stats 与 /object_info，确认服务和节点是否可用。",
        side_effects="只访问本机或配置的 ComfyUI API，不提交生成任务。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=True,
        source_projects=("IO-AtelierTech/comfyui-mcp", "artokun/comfyui-mcp"),
        invocation="python examples/comfy_bridge/probe.py --json",
    ),
    ToolCapability(
        name="comfyui.workflow_validate",
        bridge="comfyui",
        action="workflow_validate",
        maturity="implemented",
        risk_level="safe_read_only",
        description="校验 workflow JSON 是否为 API format，并检查关键节点引用。",
        side_effects="只读取公开示例 workflow 或用户明确传入的文件。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("IO-AtelierTech/comfyui-mcp", "artokun/comfyui-mcp"),
        invocation="python examples/comfy_bridge/validate_workflow.py --json",
    ),
    ToolCapability(
        name="photoshop.session_info",
        bridge="photoshop",
        action="session_info",
        maturity="experimental",
        risk_level="safe_read_only",
        description="通过 Windows COM 读取 Photoshop session 和当前文档摘要。",
        side_effects="需要已授权 Photoshop；不打开 PSD，不保存导出。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=True,
        source_projects=("loonghao/photoshop-python-api-mcp-server", "alisaitteke/photoshop-mcp"),
        invocation="powershell -ExecutionPolicy Bypass -File examples/photoshop_bridge/scripts/document_info.ps1",
    ),
    ToolCapability(
        name="photoshop.subject_extract",
        bridge="photoshop",
        action="subject_extract",
        maturity="experimental",
        risk_level="guarded_local_write",
        description="对用户明确传入的图片运行主体选择并导出测试 PNG。",
        side_effects="会打开输入图片并写出输出 PNG；输入和输出路径必须由参数传入。",
        safe_default=False,
        requires_confirmation=True,
        requires_local_software=True,
        source_projects=("loonghao/photoshop-python-api-mcp-server", "alisaitteke/photoshop-mcp"),
        next_step="后续 MCP tool 必须保留参数化路径和输出脱敏。",
    ),
    ToolCapability(
        name="illustrator.document_info",
        bridge="illustrator",
        action="document_info",
        maturity="planned",
        risk_level="safe_read_only",
        description="通过 JSX/COM 读取 Illustrator 当前文档、图层、画板和坐标系摘要。",
        side_effects="不打开私有 .ai 文件，不导出 SVG/PDF/PNG。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=True,
        source_projects=("ie3jp/illustrator-mcp-server",),
        next_step="先做只读 document_info，再评估 preflight。",
    ),
    ToolCapability(
        name="illustrator.preflight",
        bridge="illustrator",
        action="preflight",
        maturity="planned",
        risk_level="safe_read_only",
        description="检查当前 Illustrator 文档的印前风险，例如链接、颜色模式和文本问题。",
        side_effects="只读取当前文档信息；不修复、不保存。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=True,
        source_projects=("ie3jp/illustrator-mcp-server",),
        next_step="只迁移规则思想，不复制第三方 JSX 源码。",
    ),
    ToolCapability(
        name="blender.environment_probe",
        bridge="blender",
        action="probe",
        maturity="implemented",
        risk_level="safe_read_only",
        description="检查 Blender 可执行文件和可选 MCP 目录。",
        side_effects="不打开 .blend，不运行任意 Python，不下载模型。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("ahujasid/blender-mcp",),
        invocation="python examples/blender_bridge/probe.py --json",
    ),
    ToolCapability(
        name="blender.scene_probe",
        bridge="blender",
        action="scene_probe",
        maturity="planned",
        risk_level="guarded_local_process",
        description="未来用公开安全脚本启动 Blender 生成基础测试场景并验证渲染环境。",
        side_effects="会启动 Blender 进程；不得执行任意用户脚本或下载外部资产。",
        safe_default=False,
        requires_confirmation=True,
        requires_local_software=True,
        source_projects=("ahujasid/blender-mcp",),
        next_step="先做固定模板场景，不开放任意 Python 执行。",
    ),
    ToolCapability(
        name="jianying_capcut.draft_probe",
        bridge="jianying_capcut",
        action="draft_probe",
        maturity="research",
        risk_level="safe_read_only",
        description="检查剪映/CapCut 可执行文件和草稿目录配置。",
        side_effects="不读取 draft_content.json，不导出视频，不触碰账号。",
        safe_default=True,
        requires_confirmation=False,
        requires_local_software=False,
        source_projects=("sun-guannan/VectCutAPI", "xuliang2024/cutcli-cookbook"),
        invocation="python examples/capcut_jianying_bridge/probe.py --json",
    ),
)


def list_capabilities(*, bridge: str = "all", include_guarded: bool = True) -> list[dict[str, Any]]:
    selected = []
    for capability in CAPABILITIES:
        if bridge != "all" and capability.bridge not in {bridge, "all"}:
            continue
        if not include_guarded and not capability.safe_default:
            continue
        selected.append(capability.to_dict())
    return sanitize(selected)


def capability_summary(*, bridge: str = "all", include_guarded: bool = True) -> dict[str, Any]:
    capabilities = list_capabilities(bridge=bridge, include_guarded=include_guarded)
    return sanitize(
        {
            "ok": True,
            "framework": "StarBridge",
            "action": "tools",
            "bridge": bridge,
            "capability_count": len(capabilities),
            "capabilities": capabilities,
            "adoption_policy": {
                "third_party_source": "third_party_research is local-only and ignored by Git.",
                "copy_policy": "借鉴架构和接口形状；不直接复制第三方源码到公开仓库。",
                "write_policy": "写入类能力必须参数化路径、默认 dry-run 或需要用户确认。",
            },
        }
    )
