export const navigation = [
  ["/", "首页"], ["/features", "功能"], ["/editions", "版本"],
  ["/workflows", "工作流"], ["/privacy", "隐私"], ["/docs", "文档"],
  ["/roadmap", "路线图"], ["/support", "支持"]
];

export const pages = {
  "/": {
    eyebrow: "Windows 本地创意工作台",
    title: "让创意软件协同工作，而不是反复切换。",
    intro: "StarBridge 把图片矢量化、批量任务和创意软件联动集中在一个应用中。你的图片和设计文件始终留在自己的电脑里。",
    actions: [["/editions", "查看 Community 免费版"], ["/features", "了解 Pro 专业版"]],
    sections: [["先完成作品，再处理工具切换", "从图片导入、模式选择、本地执行到结果预览和任务记录，Community 工作流集中在一个桌面应用中。"], ["本机处理是产品边界", "不上传图片、设计文件或授权文件，不收集遥测，也不依赖 StarBridge 授权服务器。"], ["能力状态说清楚", "公开 MIT 能力继续属于 Community；批量、项目管理和新的私有增强仍处于专业版规划阶段。"]]
  },
  "/features": {
    eyebrow: "功能", title: "为真实创作流程组织功能。",
    intro: "页面只陈述已有证据或明确的规划状态，不把按钮、schema 或测试替代为商业交付。",
    sections: [["Community 图片矢量化", "匠心矢量、智能矢量、轻量矢量和精确重建均来自已公开 MIT 代码，可在本机执行。"], ["创意软件联动", "仓库已有 Illustrator、Photoshop、ComfyUI、Blender 与 CAD 的公开实现或协议；具体桌面验收状态以文档和 Manifest 为准。"], ["生产级矢量工作流 · 规划中", "未来 Pro 的价值来自批量队列、文件夹处理、项目历史、任务恢复、商业交付、新私有增强和专业支持。"]]
  },
  "/editions": {
    eyebrow: "版本对比", title: "免费能力直接使用，专业能力按证据开放。",
    intro: "Community 无需激活。Pro 早鸟永久版建议 ¥399，但尚未开售；Enterprise 按项目报价。",
    sections: [["Community · ¥0", "本地桌面运行、四种公开矢量模式与开放核心能力；无需登录、联网或授权文件。"], ["Pro · 建议 ¥399", "生产级矢量工作流仍在规划；价格、设备数量、更新和支持条款尚待产品所有者决定。"], ["Enterprise · 按项目报价", "企业部署、交付支持和定制代码必须通过单独合同确认；当前未开放销售。"]]
  },
  "/workflows": {
    eyebrow: "工作流案例", title: "从一张图片开始，在本机完成交付。",
    intro: "Community 主流程：导入图片 → 选择模式 → 确认参数与写入 → 本地执行 → 预览与质量指标 → 打开输出目录 → 保存任务记录。",
    sections: [["图标与 Logo", "轻量矢量强调更少的颜色、节点和文件体积。"], ["插画与品牌图形", "匠心矢量和智能矢量保留编辑性，并通过明确的质量门控拒绝不合格结果。"], ["像素级存档", "精确重建不缩放、不量化颜色，适用于需要逐像素核对的本地任务。"]]
  },
  "/privacy": {
    eyebrow: "本地处理与隐私", title: "你的素材不需要离开电脑。",
    intro: "核心运算只在本机执行，应用只绑定 loopback，不扫描未授权目录，也不收集遥测。",
    sections: [["素材", "图片和设计文件不上传到 StarBridge 服务器。"], ["授权", "Community 无需授权；未来 Pro 使用人工交付的离线签名文件，不上传授权文件。"], ["软件更新", "正式签名构建只向 GitHub Releases 请求版本信息；可关闭定时检查，下载和安装始终需要确认。"], ["写入", "运行、导出和写入继续要求显式确认，并受安全目录限制。"]]
  },
  "/docs": {
    eyebrow: "文档", title: "从产品事实到开发边界。",
    intro: "仓库文档记录功能证据、MIT 商业边界、离线授权、私有 Pro 架构和 Windows 发布门槛。",
    actions: [["https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/tree/main/docs", "打开 GitHub 文档"]],
    sections: [["产品 Manifest", "机器可读事实源区分可用、实验、规划和未支持状态。"], ["商业边界审计", "已经公开的能力继续受 MIT 许可，不改写历史。"], ["发布准备", "签名、干净机器、Defender、SmartScreen 和正式条款全部设为收费门槛。"]]
  },
  "/download": {
    eyebrow: "下载", title: "Windows 内部预览版可以直接下载。",
    intro: "StarBridge Community 0.1.0 未签名内部预览版已通过 GitHub prerelease 提供给团队测试。无需 Git、Python 或 Node.js；由于尚未完成 Authenticode，Windows 可能显示“未知发布者”。",
    actions: [["https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/releases/download/starbridge-preview-v0.1.0-unsigned.1/StarBridge-Desktop_0.1.0_x64-setup-UNSIGNED-PREVIEW.exe", "下载 Windows x64 内部预览版"], ["https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/releases/tag/starbridge-preview-v0.1.0-unsigned.1", "查看 GitHub 上传记录"]],
    sections: [["当前状态", "GitHub 公开资产可直接下载；公网重新下载后的文件已在本机完成安装、启动和 Defender 自定义扫描，检出 0。"], ["文件校验", "SHA-256：CB163DCB77CE79CDA2E815B8B8FF16760FAFCC81F0465D342B37AE1E71BB146D。"], ["版本边界", "这是团队内部预览版，不是 Authenticode 签名稳定版，也不是收费 Release。"], ["正式开放条件", "仍需完成受信任代码签名、干净 Windows、SmartScreen、升级回滚和正式条款验收。"]]
  },
  "/roadmap": {
    eyebrow: "路线图", title: "先把证据做实，再扩大承诺。",
    intro: "路线图按可验证里程碑推进，不把规划中的 Pro 或软件联动写成已交付。",
    sections: [["现在", "品牌系统、桌面 Shell、真实 Community 矢量化流程和离线授权体验。"], ["下一门槛", "私有 Pro 仓库与至少一个真实端到端商业 MVP。"], ["发布前", "代码签名、干净机器、网络请求、升级回滚、Defender 与 SmartScreen 验收。"]]
  },
  "/support": {
    eyebrow: "支持与购买说明", title: "购买尚未开放，问题可以先从文档开始。",
    intro: "Pro 价格和条款仍是建议状态；没有立即购买入口，也没有授权服务器。",
    actions: [["https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/issues", "查看公开问题"]],
    sections: [["Community", "公开问题区用于可复现的 Community 缺陷和文档问题，请勿上传客户素材或授权文件。"], ["Pro", "专业支持渠道、期限和响应承诺尚待产品所有者决定。"], ["Enterprise", "企业部署和定制必须单独确认范围、安全边界、交付证据和合同。"]]
  }
};
