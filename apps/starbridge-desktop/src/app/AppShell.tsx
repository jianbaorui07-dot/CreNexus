import type { ReactNode } from "react";

import { Brand } from "../components/Brand/Brand";
import { EditionBadge } from "../components/EditionBadge/EditionBadge";
import { Navigation } from "../components/Navigation/Navigation";
import { StatusChip } from "../components/StatusChip/StatusChip";
import type { ConnectionOverview, LicenseStatus, RuntimeStatus, SoftwareUpdateStatus, VersionInfo } from "../types/api";
import { PAGE_TITLES, type PageId } from "./routes";

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
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <Navigation currentPage={currentPage} onNavigate={onNavigate} />
        <div className="sidebar-footnote">
          <span aria-hidden="true">✓</span>
          <p><strong>本机处理</strong><br />不上传图片和设计文件</p>
        </div>
      </aside>
      <section className="app-main">
        <header className="app-topbar">
          <div>
            <span className="topbar-product">StarBridge</span>
            <h1>{PAGE_TITLES[currentPage]}</h1>
          </div>
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
              onClick={() => void onOpenGitHub()}
              title="打开 StarBridge GitHub 项目"
            >
              GitHub 项目
            </button>
            <StatusChip state={status.state} />
            <EditionBadge edition={license.edition} />
            <span className="version-copy">v{version?.desktop ?? "—"}</span>
            <button type="button" className="icon-button settings-button" aria-label="打开设置与诊断" onClick={() => onNavigate("diagnostics")}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19 13.5v-3l-2-.7a6 6 0 0 0-.6-1.4l.9-1.9-2.1-2.1-1.9.9a6 6 0 0 0-1.4-.6L11.2 3h-3l-.7 2a6 6 0 0 0-1.4.6l-1.9-.9-2.1 2.1.9 1.9a6 6 0 0 0-.6 1.4l-2 .7v3l2 .7a6 6 0 0 0 .6 1.4l-.9 1.9 2.1 2.1 1.9-.9a6 6 0 0 0 1.4.6l.7 2h3l.7-2a6 6 0 0 0 1.4-.6l1.9.9 2.1-2.1-.9-1.9a6 6 0 0 0 .6-1.4z" /></svg>
            </button>
          </div>
        </header>
        <main className="page-content">{children}</main>
      </section>
    </div>
  );
}
