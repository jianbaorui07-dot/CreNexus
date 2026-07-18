import type { ReactNode } from "react";
import { IconBrandGithub, IconSettings } from "@tabler/icons-react";

import { Brand } from "../components/Brand/Brand";
import { EditionBadge } from "../components/EditionBadge/EditionBadge";
import { Navigation } from "../components/Navigation/Navigation";
import { StatusChip } from "../components/StatusChip/StatusChip";
import type { ConnectionOverview, LicenseStatus, RuntimeStatus, SoftwareUpdateStatus, VersionInfo } from "../types/api";
import { NAVIGATION_ITEMS, PAGE_CAPTIONS, PAGE_TITLES, type PageId } from "./routes";

interface AppShellProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  status: RuntimeStatus;
  connections: ConnectionOverview | null;
  license: LicenseStatus;
  version: VersionInfo | null;
  updateStatus: SoftwareUpdateStatus;
  onOpenGitHub: () => Promise<void>;
  children: ReactNode;
}

export function AppShell({ currentPage, onNavigate, status, connections, license, version, updateStatus, onOpenGitHub, children }: AppShellProps) {
  const pageIndex = NAVIGATION_ITEMS.findIndex((item) => item.id === currentPage);
  const readyApplications = connections?.applications.filter((application) => application.bridge_available).length ?? 0;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <Navigation currentPage={currentPage} onNavigate={onNavigate} />
        <div className="sidebar-footnote">
          <span>LOCAL RUNTIME / 本机摘要</span>
          <dl>
            <div><dt>运行</dt><dd>{status.state === "connected" ? "ONLINE" : status.state.toUpperCase()}</dd></div>
            <div><dt>Codex</dt><dd>{connections?.codex.session_paired ? "PAIRED" : "STANDBY"}</dd></div>
            <div><dt>软件桥</dt><dd>{readyApplications} READY</dd></div>
            <div><dt>数据</dt><dd>LOCAL-ONLY</dd></div>
          </dl>
          <p><strong>PRIVATE BY DESIGN</strong><br />不上传图片和设计文件</p>
        </div>
      </aside>
      <section className="app-main">
        <header className="app-topbar">
          <div className="topbar-page-title">
            <span className="topbar-index">{pageIndex >= 0 ? String(pageIndex + 1).padStart(2, "0") : "—"}</span>
            <h1>{PAGE_TITLES[currentPage]}</h1>
            <span className="topbar-caption">/ {PAGE_CAPTIONS[currentPage]}</span>
          </div>
          <div className="workspace-marker"><span>WORKSPACE</span><strong>LOCAL CREATIVE WORKSPACE</strong></div>
          <div className="topbar-actions">
            <button
              type="button"
              className={connections?.drawing_enabled ? "codex-topbar-chip is-connected" : "codex-topbar-chip"}
              onClick={() => onNavigate("integrations")}
              title="打开连接中心"
            >
              <span aria-hidden="true" />
              {connections?.drawing_enabled ? "Codex 已关联" : "Codex 待关联"}
            </button>
            {updateStatus.available && updateStatus.version ? (
              <button
                type="button"
                className="update-available-button"
                onClick={() => onNavigate("diagnostics")}
              >
                可更新至 v{updateStatus.version}
              </button>
            ) : null}
            <button
              type="button"
              className="github-project-button"
              aria-label="GitHub 项目"
              onClick={() => void onOpenGitHub()}
              title="打开 CreNexus GitHub 项目"
            >
              <IconBrandGithub aria-hidden="true" />
              <span>GitHub</span>
            </button>
            <StatusChip state={status.state} />
            <EditionBadge edition={license.edition} />
            <span className="version-copy">v{version?.desktop ?? "—"}</span>
            <button type="button" className="icon-button settings-button" aria-label="打开设置与诊断" onClick={() => onNavigate("diagnostics")}>
              <IconSettings aria-hidden="true" />
            </button>
          </div>
        </header>
        <main className="page-content">{children}</main>
        <footer className="app-statusbar">
          <span>LOCAL-FIRST</span>
          <span>SAFE ROOTS ENABLED</span>
          <span>{status.state === "connected" ? "RUNTIME ONLINE" : "RUNTIME CHECK"}</span>
          <button type="button" onClick={() => onNavigate("diagnostics")}>设置与诊断 →</button>
        </footer>
      </section>
    </div>
  );
}
