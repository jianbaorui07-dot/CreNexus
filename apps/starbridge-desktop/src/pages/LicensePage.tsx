import { useState, type ChangeEvent } from "react";

import { ErrorState } from "../components/ErrorState/ErrorState";
import type { StarBridgeClient } from "../services/client";
import type { LicenseStatus, VersionInfo } from "../types/api";

const FEATURE_LABELS: Record<string, string> = {
  "vectorization.advanced": "公开矢量模式兼容项",
  "workflow.production_vector": "生产级矢量工作流",
  "batch.processing": "生产级批量处理",
  "integration.adobe": "Adobe 商业工作流增强",
  "integration.comfyui": "ComfyUI 商业工作流增强",
  "integration.blender": "Blender 商业工作流增强",
  "updates.offline_signed_packages": "签名离线更新包",
  "support.enterprise_customization": "企业定制支持",
};

interface LicensePageProps {
  client: StarBridgeClient;
  license: LicenseStatus;
  version: VersionInfo | null;
  onLicenseChanged: (license: LicenseStatus) => void;
}

export function LicensePage({ client, license, version, onLicenseChanged }: LicensePageProps) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const exportRequest = async () => {
    setBusy(true);
    setMessage("");
    try {
      const receipt = await client.createLicenseRequest();
      setMessage(`${receipt.fileName} 已保存到本机授权申请目录${receipt.folderOpened ? "，文件夹已打开。" : "。"}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "设备申请没有创建；请稍后重试。");
    } finally {
      setBusy(false);
    }
  };

  const importLicense = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    if (file.size === 0) {
      setMessage("授权文件为空。请重新取得完整的授权文件后再导入。");
      return;
    }
    if (file.size > 64 * 1024) {
      setMessage("授权文件超过 64 KB，已拒绝读取。请确认选择的是 StarBridge 授权文件。");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const next = await client.importLicenseFile(await file.text());
      onLicenseChanged(next);
      setMessage("授权文件已在本机完成签名和设备绑定验证。");
    } catch (error) {
      setMessage(error instanceof Error ? `${error.message} 请核对购买确认单或重新取得授权文件。` : "授权文件没有导入；请重新取得授权文件后再试。");
    } finally {
      setBusy(false);
    }
  };

  const exportSummary = () => {
    if (license.state !== "active") return;
    const lines = [
      "StarBridge 授权摘要",
      `版本：${license.edition}`,
      `授权编号：${license.licenseId ?? "未提供"}`,
      `签发日期：${license.issuedOn ?? "未提供"}`,
      `设备数量：${license.deviceLimit}`,
      `当前设备：${license.currentDeviceMatched ? "匹配" : "未匹配"}`,
      `永久授权：${license.perpetual ? "是" : "否"}`,
      `功能：${license.features.map((feature) => FEATURE_LABELS[feature] ?? "商业扩展功能").join("、")}`,
      "说明：此摘要不包含设备指纹、授权签名、公钥或授权文件内容。",
    ];
    const url = URL.createObjectURL(new Blob([`${lines.join("\n")}\n`], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "StarBridge-license-summary.txt";
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage("已导出脱敏授权摘要。");
  };

  return (
    <div className="standard-page license-page">
      <header className="page-intro"><div><span className="page-kicker">版本与授权</span><h2>{license.state === "active" ? `${license.edition === "enterprise" ? "Enterprise 企业版" : "Pro 专业版"}已激活` : "Community 免费版"}</h2><p>{license.state === "active" ? license.message : "你可以直接使用免费功能，无需登录、无需联网，也不需要授权文件。"}</p></div><span className={`large-edition edition-${license.edition}`}>{license.edition === "community" ? "Community" : license.edition === "pro" ? "Pro" : "Enterprise"}</span></header>

      {license.state !== "active" ? <>
        {license.state === "invalid" ? <ErrorState title="授权文件未生效" message={`${license.message || "当前授权文件没有通过本机验证。"} Community 免费功能仍可继续使用。`} nextSteps={["重新导入从人工购买渠道取得的原始授权文件。", "如更换过设备，请保留购买确认单并联系人工支持。"]} /> : null}
        <section className="community-summary">
          <div><span className="summary-icon" aria-hidden="true">✓</span><div><h3>免费功能可直接使用</h3><p>当前版本 {version?.desktop ?? "—"} · 四种公开矢量模式 · 本机处理 · 无需激活</p></div></div>
          <ul><li>不使用授权服务器</li><li>不收集遥测</li><li>图片与设计文件留在本机</li></ul>
        </section>
        <section className="pro-overview">
          <div className="section-heading"><div><span>了解 Pro 专业版</span><h3>建议 ¥399 早鸟永久版</h3></div><span className="proposed-price">建议方案 · 尚未开售</span></div>
          <p>Pro 的价值来自未来新的生产级矢量工作流：批量、自动化、项目管理、商业交付、私有增强、稳定安装包和专业支持。公开的四种矢量模式不会被重新包装为 Pro 独占能力。</p>
          <div className="activation-steps">
            <article><span>1</span><h4>导出设备申请</h4><p>生成脱敏申请文件，不含原始 MachineGuid、图片、授权文件或私钥。请按购买说明发送给 StarBridge 人工处理。</p><button type="button" className="secondary" disabled={busy} onClick={() => void exportRequest()}>导出设备申请</button></article>
            <article><span>2</span><h4>完成人工购买</h4><p>价格与条款仍是建议状态。正式开售前会明确 1–2 台设备、换机、退款、更新和支持期限。</p><span className="inactive-action">当前尚未开放购买</span></article>
            <article><span>3</span><h4>导入授权文件</h4><p>收到签名授权后在本机导入。验证通过后保存在 StarBridge 应用数据目录，不会上传。</p><label className={`file-button${busy ? " is-disabled" : ""}`}>导入授权文件<input type="file" disabled={busy} accept=".starbridge-license,application/json" onChange={(event) => void importLicense(event)} /></label></article>
          </div>
          <p className="device-note">设备与换机规则尚待产品所有者决定；当前协议上限为 2 台设备。重装或主板更换不能擅自承诺自动解绑。</p>
        </section>
      </> : <section className="active-license-panel">
        <div className="license-valid"><span aria-hidden="true">✓</span><div><h3>授权签名与当前设备已匹配</h3><p>验证完全在本机进行，没有联系授权服务器。</p></div></div>
        <dl className="license-detail-grid">
          <div><dt>授权版本</dt><dd>{license.edition === "enterprise" ? "Enterprise" : "Pro"}</dd></div>
          <div><dt>授权编号</dt><dd>{license.licenseId ?? "已脱敏"}</dd></div>
          <div><dt>设备数量</dt><dd>{license.deviceLimit} 台</dd></div>
          <div><dt>当前设备</dt><dd>{license.currentDeviceMatched ? "已匹配" : "未匹配"}</dd></div>
          <div><dt>永久授权</dt><dd>{license.perpetual ? "有效" : "未确认"}</dd></div>
          <div><dt>更新权益</dt><dd>以购买确认单为准</dd></div>
          <div><dt>支持权益</dt><dd>以购买确认单为准</dd></div>
        </dl>
        <div className="unlocked-features"><h3>已解锁功能</h3><ul>{license.features.map((feature) => <li key={feature}>✓ {FEATURE_LABELS[feature] ?? "商业扩展功能"}</li>)}</ul></div>
        <div className="actions"><button type="button" className="secondary" onClick={exportSummary}>导出授权摘要</button><button type="button" className="quiet-button" onClick={() => setMessage("换机与解绑规则尚未正式确定。请保留购买确认单并联系人工支持。")}>查看换机说明</button></div>
      </section>}
      {message ? <p className="page-message" role="status">{message}</p> : null}
      {!license.commercialVerifierConfigured ? <details className="development-note"><summary>开发构建技术说明</summary><p>当前公开构建没有商业验签公钥，也不包含私有 Pro 功能代码。Community 功能不受影响。</p></details> : null}
    </div>
  );
}
