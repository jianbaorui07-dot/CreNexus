import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BatchPage } from "../pages/BatchPage";
import { ComfyUiGenerationPage } from "../pages/ComfyUiGenerationPage";
import { DeliveryPage } from "../pages/DeliveryPage";
import { DiagramForgePage } from "../pages/DiagramForgePage";
import { DiagnosticsPage } from "../pages/DiagnosticsPage";
import { HomePage } from "../pages/HomePage";
import { IntegrationsPage } from "../pages/IntegrationsPage";
import { JobDetailPage } from "../pages/JobDetailPage";
import { LicensePage } from "../pages/LicensePage";
import { PhotoshopProductionPage } from "../pages/PhotoshopProductionPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { TasksPage } from "../pages/TasksPage";
import { VectorizationPage } from "../pages/VectorizationPage";
import { WorkflowsPage } from "../pages/WorkflowsPage";
import { CreNexusApiClient, UserFacingError, type CreNexusClient } from "../services/client";
import type {
  ConnectionOverview,
  LicenseStatus,
  CreativeJob,
  RuntimeStatus,
  SoftwareUpdateProgress,
  SoftwareUpdateStatus,
  VersionInfo,
} from "../types/api";
import { AppShell } from "./AppShell";
import type { PageId } from "./routes";

const INITIAL_STATUS: RuntimeStatus = {
  state: "starting",
  message: "正在准备本机创意工作台。",
  recoveryAttempts: 0,
};

const INITIAL_LICENSE: LicenseStatus = {
  state: "community",
  edition: "community",
  message: "Community 免费版正在本机运行，不需要授权文件。",
  deviceLimit: 0,
  features: [],
  commercialVerifierConfigured: false,
};

const INITIAL_UPDATE_STATUS: SoftwareUpdateStatus = {
  configured: false,
  source: "GitHub Releases",
  currentVersion: "0.1.0-alpha.1",
  available: false,
  signatureRequired: true,
  automaticChecksSupported: false,
};
const UPDATE_CHECK_PREFERENCE = "starbridge.update.automaticChecks";
const UPDATE_CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000;

interface AppProps {
  client?: CreNexusClient;
}

function statusFromError(error: unknown): RuntimeStatus {
  if (error instanceof UserFacingError) {
    return {
      state: error.code === "backend_offline" ? "offline" : "failed",
      message: error.message,
      recoveryAttempts: 0,
      technicalDetails: error.technicalDetails,
    };
  }
  return {
    state: "failed",
    message: "本地服务状态暂时无法确认。请在设置与诊断中重新启动。",
    recoveryAttempts: 0,
    technicalDetails: error instanceof Error ? error.message : String(error),
  };
}

export function App({ client: providedClient }: AppProps) {
  const client = useMemo(() => providedClient ?? new CreNexusApiClient(), [providedClient]);
  const [page, setPage] = useState<PageId>("home");
  const [status, setStatus] = useState<RuntimeStatus>(INITIAL_STATUS);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [license, setLicense] = useState<LicenseStatus>(INITIAL_LICENSE);
  const [tasks, setTasks] = useState<CreativeJob[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const [connections, setConnections] = useState<ConnectionOverview | null>(null);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState("");
  const [updateStatus, setUpdateStatus] = useState<SoftwareUpdateStatus>(INITIAL_UPDATE_STATUS);
  const [automaticUpdateChecks, setAutomaticUpdateChecks] = useState(
    () => window.localStorage.getItem(UPDATE_CHECK_PREFERENCE) !== "false",
  );
  const [checkingForUpdate, setCheckingForUpdate] = useState(false);
  const [installingUpdate, setInstallingUpdate] = useState(false);
  const [updateProgress, setUpdateProgress] = useState<SoftwareUpdateProgress | null>(null);
  const [updateMessage, setUpdateMessage] = useState("");
  const [updateError, setUpdateError] = useState("");
  const mounted = useRef(true);
  const updateCheckInFlight = useRef(false);
  const connectionCheckInFlight = useRef(false);

  const refreshStatus = useCallback(async () => {
    try {
      const next = await client.getRuntimeStatus();
      if (mounted.current) setStatus(next);
    } catch (error) {
      if (mounted.current) setStatus(statusFromError(error));
    }
  }, [client]);

  const refreshConnections = useCallback(async () => {
    if (connectionCheckInFlight.current) return;
    connectionCheckInFlight.current = true;
    setConnectionsLoading(true);
    setConnectionsError("");
    try {
      const next = await client.getConnections();
      if (mounted.current) setConnections(next);
    } catch (error) {
      if (mounted.current) {
        setConnectionsError(
          error instanceof Error ? error.message : "暂时无法读取连接状态。",
        );
      }
    } finally {
      connectionCheckInFlight.current = false;
      if (mounted.current) setConnectionsLoading(false);
    }
  }, [client]);

  const checkForUpdates = useCallback(async () => {
    if (updateCheckInFlight.current) return;
    updateCheckInFlight.current = true;
    setCheckingForUpdate(true);
    setUpdateError("");
    try {
      const next = await client.checkForUpdate();
      if (!mounted.current) return;
      setUpdateStatus(next);
      setUpdateMessage(
        next.available && next.version
          ? `发现 CreNexus v${next.version}，请查看版本说明后确认安装。`
          : "当前已经是最新正式版本。",
      );
    } catch (error) {
      if (!mounted.current) return;
      setUpdateError(
        error instanceof Error
          ? error.message
          : "暂时无法检查更新；当前版本可以继续离线使用。",
      );
    } finally {
      updateCheckInFlight.current = false;
      if (mounted.current) setCheckingForUpdate(false);
    }
  }, [client]);

  const changeAutomaticUpdateChecks = useCallback((enabled: boolean) => {
    setAutomaticUpdateChecks(enabled);
    window.localStorage.setItem(UPDATE_CHECK_PREFERENCE, String(enabled));
    setUpdateMessage(enabled ? "已开启定时检查；下载和安装仍需要你确认。" : "已关闭定时检查；仍可手动检查更新。");
  }, []);

  const installUpdate = useCallback(async () => {
    if (!updateStatus.version) return;
    setInstallingUpdate(true);
    setUpdateProgress(null);
    setUpdateError("");
    setUpdateMessage("正在下载并验证更新包。请保持 CreNexus 打开。");
    try {
      await client.installUpdate(updateStatus.version, true, (event) => {
        if (mounted.current) setUpdateProgress(event);
      });
    } catch (error) {
      if (mounted.current) {
        setInstallingUpdate(false);
        setUpdateError(
          error instanceof Error
            ? error.message
            : "更新未完成；当前版本已保留，可以继续使用。",
        );
      }
    }
  }, [client, updateStatus.version]);

  const refreshTasks = useCallback(async () => {
    try {
      const jobs = await client.getCreativeJobs();
      if (mounted.current) setTasks(jobs);
    } catch {
      // History is secondary; an offline state is already visible in the shell.
    }
  }, [client]);

  useEffect(() => {
    mounted.current = true;
    void refreshStatus();
    void client.getVersion().then((next) => mounted.current && setVersion(next)).catch(() => undefined);
    void client.getLicenseStatus().then((next) => mounted.current && setLicense(next)).catch(() => undefined);
    void client.getUpdateStatus().then((next) => mounted.current && setUpdateStatus(next)).catch(() => undefined);
    return () => { mounted.current = false; };
  }, [client, refreshStatus]);

  useEffect(() => {
    if (!automaticUpdateChecks || !updateStatus.configured) return undefined;
    const initialCheck = window.setTimeout(() => void checkForUpdates(), 2500);
    const periodicCheck = window.setInterval(() => void checkForUpdates(), UPDATE_CHECK_INTERVAL_MS);
    return () => {
      window.clearTimeout(initialCheck);
      window.clearInterval(periodicCheck);
    };
  }, [automaticUpdateChecks, checkForUpdates, updateStatus.configured]);

  useEffect(() => {
    if (status.state === "starting" || status.state === "recovering") {
      const timer = window.setTimeout(() => void refreshStatus(), 600);
      return () => window.clearTimeout(timer);
    }
    if (status.state === "connected") {
      void refreshTasks();
      void refreshConnections();
    }
    return undefined;
  }, [refreshConnections, refreshStatus, refreshTasks, status.state]);

  useEffect(() => {
    if (
      page !== "integrations"
      || status.state !== "connected"
      || connections?.drawing_enabled
    ) return undefined;
    const timer = window.setInterval(() => void refreshConnections(), 1800);
    return () => window.clearInterval(timer);
  }, [connections?.drawing_enabled, page, refreshConnections, status.state]);

  const restart = useCallback(async () => {
    setConnections(null);
    setStatus((current) => ({ ...current, state: "recovering", message: "正在重新启动本地服务。" }));
    try {
      setStatus(await client.restartBackend());
    } catch (error) {
      setStatus(statusFromError(error));
    }
  }, [client]);

  const renderPage = () => {
    const openWorkflow = (projectId?: string, workflowId = "vector-delivery-v1") => {
      setSelectedProjectId(projectId);
      setPage(
        workflowId === "comfyui-generation-v1"
          ? "ai-generation"
          : workflowId === "photoshop-production-v1"
            ? "photoshop-production"
            : "workflows",
      );
    };
    const openJob = (jobId: string, projectId: string) => {
      setSelectedJobId(jobId);
      setSelectedProjectId(projectId);
      setPage("job-detail");
    };
    const openDelivery = (projectId: string) => {
      setSelectedProjectId(projectId);
      setPage("delivery");
    };
    switch (page) {
      case "home":
        return <HomePage status={status} connections={connections} recentTasks={tasks} license={license} version={version} onNavigate={setPage} />;
      case "projects":
        return <ProjectsPage client={client} runtimeReady={status.state === "connected"} onOpenWorkflow={openWorkflow} />;
      case "workflows":
      case "vectorization":
        if (connections?.drawing_enabled !== true) {
          return <IntegrationsPage client={client} connections={connections} loading={connectionsLoading} error={connectionsError} onRefresh={refreshConnections} onRestartBridge={restart} />;
        }
        return <WorkflowsPage client={client} runtimeReady={status.state === "connected"} initialProjectId={selectedProjectId} onOpenProjects={() => setPage("projects")} onOpenJob={openJob} />;
      case "diagramforge":
        return <DiagramForgePage />;
      case "ai-generation":
        if (connections?.drawing_enabled !== true) {
          return <IntegrationsPage client={client} connections={connections} loading={connectionsLoading} error={connectionsError} onRefresh={refreshConnections} onRestartBridge={restart} />;
        }
        return <ComfyUiGenerationPage client={client} runtimeReady={status.state === "connected"} initialProjectId={selectedProjectId} onOpenJob={openJob} />;
      case "photoshop-production":
        return <PhotoshopProductionPage client={client} runtimeReady={status.state === "connected"} initialProjectId={selectedProjectId} onOpenJob={openJob} />;
      case "legacy-vectorization":
        return <VectorizationPage
          client={client}
          runtimeReady={status.state === "connected"}
          codexConnected={connections?.drawing_enabled === true}
          onOpenConnections={() => setPage("integrations")}
          onTaskSaved={() => void refreshTasks()}
        />;
      case "batch":
        return <BatchPage />;
      case "integrations":
        return <IntegrationsPage
          client={client}
          connections={connections}
          loading={connectionsLoading}
          error={connectionsError}
          onRefresh={refreshConnections}
          onRestartBridge={restart}
        />;
      case "tasks":
        return <TasksPage tasks={tasks} onStart={() => openWorkflow()} onOpenJob={openJob} />;
      case "job-detail":
        return <JobDetailPage client={client} jobId={selectedJobId} onOpenDelivery={openDelivery} onBack={() => setPage("tasks")} onJobChanged={() => void refreshTasks()} />;
      case "delivery":
        return <DeliveryPage client={client} initialProjectId={selectedProjectId} />;
      case "license":
        return <LicensePage client={client} license={license} version={version} onLicenseChanged={setLicense} />;
      case "diagnostics":
        return <DiagnosticsPage
          status={status}
          version={version}
          onRestart={restart}
          onOpenLogs={() => client.openLogsDirectory()}
          updateStatus={updateStatus}
          automaticUpdateChecks={automaticUpdateChecks}
          checkingForUpdate={checkingForUpdate}
          installingUpdate={installingUpdate}
          updateProgress={updateProgress}
          updateMessage={updateMessage}
          updateError={updateError}
          onAutomaticUpdateChecksChange={changeAutomaticUpdateChecks}
          onCheckForUpdate={checkForUpdates}
          onInstallUpdate={installUpdate}
        />;
    }
  };

  return (
    <AppShell currentPage={page} onNavigate={setPage} status={status} connections={connections} license={license} version={version} updateStatus={updateStatus} onOpenGitHub={() => client.openGitHubProject()}>
      {renderPage()}
    </AppShell>
  );
}
