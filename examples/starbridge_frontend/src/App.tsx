import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import {
  Activity,
  Boxes,
  CheckCircle2,
  FileJson,
  Gauge,
  GitBranch,
  Layers3,
  LockKeyhole,
  MonitorCog,
  Play,
  Radar,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from 'lucide-react';
import * as THREE from 'three';

type Capability = {
  name: string;
  bridge: string;
  action: string;
  safe_default: boolean;
  requires_confirmation: boolean;
  current_status: string;
  risk_level: string;
};

type BridgeOverview = {
  display_name: string;
  software: string;
  tool_count: number;
  safe_default_tool_count: number;
  guarded_tool_count: number;
  statuses: string[];
  risk_levels: string[];
  safe_tools: string[];
  guarded_tools: string[];
  readiness?: string;
  safety_boundary?: string;
};

type Recipe = {
  recipe_id: string;
  bridge: string;
  goal: string;
  safe_default: boolean;
  writes: boolean;
  quality_gates: string[];
};

type CatalogItem = Recipe & {
  sku: string;
  title: string;
  tier: string;
  price_signal: string;
  buyer: string;
  install_state: string;
};

type ProductTier = {
  id: string;
  name: string;
  audience: string;
  included: string[];
  limits: string[];
};

type HybridLane = {
  id: string;
  label: string;
  bridges: string[];
  execution_target: string;
  billing_unit: string;
  safety: string;
};

type AuditEvent = {
  event_id: string;
  created_at: string;
  kind: string;
  recipe_id: string;
  bridge: string;
  action: string;
  ok: boolean;
  status: string;
  evidence_ready: boolean;
  quality_gate_count: number;
  execution_target?: string;
  summary?: string;
};

type BackendPayload = {
  capabilities: {
    capability_count: number;
    bridge_overview: Record<string, BridgeOverview>;
    capabilities: Capability[];
    planner_hints: {
      safe_discovery_sequence: string[];
      evidence_tools: string[];
    };
  };
  recipes: {
    recipes: Recipe[];
  };
  catalog: {
    catalog_version: string;
    item_count: number;
    items: CatalogItem[];
    monetization_model: string[];
  };
  tiers: {
    tiers_version: string;
    tiers: ProductTier[];
  };
  hybrid: {
    architecture_version: string;
    policy: string;
    lanes: HybridLane[];
  };
  history: {
    history_version: string;
    event_count: number;
    events: AuditEvent[];
  };
  safe_roots: {
    roots: Array<{ path: string; writable?: boolean; purpose?: string }>;
  };
  resources: {
    resources: Array<{ uri: string; title: string; mimeType: string }>;
  };
};

type ToolResult = Record<string, unknown> | null;

function defaultApiBase() {
  if (import.meta.env.DEV) return 'http://127.0.0.1:8765';
  return window.location.origin;
}

const API_BASE = ((import.meta.env.VITE_STARBRIDGE_API_URL as string | undefined) ?? defaultApiBase()).replace(/\/$/, '');

const bridgeColors: Record<string, string> = {
  all: '#f4d35e',
  comfyui: '#24c6dc',
  blender: '#f28d35',
  autocad: '#6ee7a8',
  autocad_dxf: '#8ee3ef',
  photoshop: '#4ea4ff',
  illustrator: '#ff9f43',
  jianying_capcut: '#d892ff',
};

const bridgeLabels: Record<string, string> = {
  all: '全局能力',
  comfyui: '图像生成',
  blender: '三维场景',
  autocad: 'CAD 桌面',
  autocad_dxf: 'DXF 离线',
  photoshop: '图像编辑',
  illustrator: '矢量设计',
  jianying_capcut: '视频剪辑',
};

function recipeMatchesBridge(recipe: Recipe, bridge: string) {
  if (bridge === 'all') return true;
  if (bridge === 'autocad') return recipe.bridge === 'autocad' || recipe.bridge === 'autocad_dxf';
  return recipe.bridge === bridge;
}

function ArtField({ activeColor }: { activeColor: string }) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 700);
    camera.position.set(0, 7, 44);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const count = 6200;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const accent = new THREE.Color(activeColor);
    const cyan = new THREE.Color('#87f7ff');
    const gold = new THREE.Color('#f4d35e');

    for (let index = 0; index < count; index += 1) {
      const stride = index * 3;
      const spiral = index * 0.053;
      const radius = 4 + (index % 180) * 0.105;
      const layer = Math.floor(index / 180);

      positions[stride] = Math.cos(spiral) * radius;
      positions[stride + 1] = Math.sin(layer * 0.55) * 5.5 + Math.sin(spiral * 0.7) * 1.5;
      positions[stride + 2] = Math.sin(spiral) * radius + (layer - 17) * 0.9;

      const color = (index % 5 === 0 ? gold : cyan).clone().lerp(accent, (index % 13) / 16);
      colors[stride] = color.r;
      colors[stride + 1] = color.g;
      colors[stride + 2] = color.b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.075,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);

    const ribbon = new THREE.Group();
    for (let ring = 0; ring < 7; ring += 1) {
      const curve = new THREE.EllipseCurve(0, 0, 7 + ring * 3.4, 4.5 + ring * 1.2, 0, Math.PI * 1.72);
      const curvePoints = curve.getPoints(120).map((point) => new THREE.Vector3(point.x, ring * 1.4 - 4, point.y));
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curvePoints),
        new THREE.LineBasicMaterial({
          color: ring % 2 ? activeColor : '#87f7ff',
          transparent: true,
          opacity: 0.16 + ring * 0.05,
        }),
      );
      line.rotation.x = Math.PI * 0.62;
      ribbon.add(line);
    }
    scene.add(ribbon);

    let frame = 0;
    let disposed = false;
    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const shouldAnimate = () => !disposed && !document.hidden && !motionPreference.matches;

    const resize = () => {
      const width = Math.max(container.clientWidth, 1);
      const height = Math.max(container.clientHeight, 1);
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      if (!shouldAnimate()) renderer.render(scene, camera);
    };

    const animate = () => {
      frame = 0;
      if (!shouldAnimate()) return;
      const time = performance.now() * 0.00016;
      points.rotation.y = time;
      points.rotation.x = Math.sin(time * 1.9) * 0.06;
      ribbon.rotation.y = -time * 1.25;
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };

    const syncAnimation = () => {
      if (shouldAnimate()) {
        if (!frame) frame = requestAnimationFrame(animate);
        return;
      }
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      renderer.render(scene, camera);
    };

    resize();
    syncAnimation();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', syncAnimation);
    motionPreference.addEventListener('change', syncAnimation);

    return () => {
      disposed = true;
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', syncAnimation);
      motionPreference.removeEventListener('change', syncAnimation);
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
      geometry.dispose();
      material.dispose();
      ribbon.children.forEach((child) => {
        const line = child as THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>;
        line.geometry.dispose();
        line.material.dispose();
      });
      renderer.dispose();
      renderer.forceContextLoss();
    };
  }, [activeColor]);

  return <div className="art-field" ref={mountRef} aria-hidden="true" />;
}

function App() {
  const [payload, setPayload] = useState<BackendPayload | null>(null);
  const [activeBridge, setActiveBridge] = useState('all');
  const [selectedRecipe, setSelectedRecipe] = useState<string | null>(null);
  const [toolResult, setToolResult] = useState<ToolResult>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [confirmRun, setConfirmRun] = useState(false);
  const [executionTarget, setExecutionTarget] = useState('local');
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadBootstrap = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/bootstrap`);
      const json = await response.json();
      if (!response.ok || !json.ok) throw new Error(json.error || 'Backend bootstrap failed');
      setPayload(json.data);
      setAuditEvents(json.data.history?.events ?? []);
      const firstRecipe = json.data.recipes.recipes[0]?.recipe_id ?? null;
      setSelectedRecipe((current) => current ?? firstRecipe);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to reach backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBootstrap();
  }, []);

  const bridgeEntries = useMemo(() => {
    if (!payload) return [];
    return Object.entries(payload.capabilities.bridge_overview).filter(([, overview]) => overview.tool_count > 0);
  }, [payload]);

  const recipes = payload?.recipes.recipes ?? [];
  const catalogItems = payload?.catalog.items ?? [];
  const productTiers = payload?.tiers.tiers ?? [];
  const hybridLanes = payload?.hybrid.lanes ?? [];
  const activeOverview = payload?.capabilities.bridge_overview[activeBridge];
  const activeColor = bridgeColors[activeBridge] ?? '#87f7ff';
  const visibleRecipes = useMemo(
    () => recipes.filter((recipe) => recipeMatchesBridge(recipe, activeBridge)),
    [activeBridge, recipes],
  );
  const visibleCatalogItems = useMemo(
    () => catalogItems.filter((item) => recipeMatchesBridge(item, activeBridge)),
    [activeBridge, catalogItems],
  );
  const activeRecipe = recipes.find((recipe) => recipe.recipe_id === selectedRecipe) ?? null;
  const activeCatalogItem = catalogItems.find((item) => item.recipe_id === selectedRecipe) ?? null;
  const supportedLanes = activeRecipe ? hybridLanes.filter((lane) => lane.bridges.includes(activeRecipe.bridge)) : [];
  const activeLane = supportedLanes.find((lane) => lane.execution_target === executionTarget) ?? supportedLanes[0];

  useEffect(() => {
    if (!visibleRecipes.length) {
      setSelectedRecipe(null);
      return;
    }
    if (!visibleRecipes.some((recipe) => recipe.recipe_id === selectedRecipe)) {
      setSelectedRecipe(visibleRecipes[0].recipe_id);
    }
  }, [selectedRecipe, visibleRecipes]);

  useEffect(() => {
    if (!activeRecipe) return;
    setExecutionTarget(activeRecipe.bridge === 'comfyui' ? 'cloud' : 'local');
    setConfirmRun(false);
  }, [activeRecipe?.recipe_id]);

  const runRecipeAction = async (action: 'plan' | 'evidence' | 'run') => {
    if (!selectedRecipe) return;
    setBusyAction(action);
    setToolResult(null);
    setError(null);
    try {
      const request: RequestInit = { method: 'POST' };
      if (action === 'run') {
        request.headers = { 'Content-Type': 'application/json' };
        request.body = JSON.stringify({ confirm_run: confirmRun, execution_target: executionTarget });
      }
      const response = await fetch(`${API_BASE}/api/recipes/${selectedRecipe}/${action}`, request);
      const json = await response.json();
      if (!response.ok || !json.ok) throw new Error(json.error || `${action} failed`);
      setToolResult(json.data);
      if (json.event) {
        setAuditEvents((current) => [json.event, ...current.filter((event) => event.event_id !== json.event.event_id)].slice(0, 30));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Unable to run ${action}`);
    } finally {
      setBusyAction(null);
    }
  };

  const clearAuditHistory = async () => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/audit/history`, { method: 'DELETE' });
      const json = await response.json();
      if (!response.ok || !json.ok) throw new Error(json.error || 'Unable to clear history');
      setAuditEvents([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to clear history');
    }
  };

  return (
    <main className="app-shell">
      <ArtField activeColor={activeColor} />
      <div className="grid-veil" />

      <aside className="side-rail" aria-label="StarBridge">
        <div className="rail-mark" title="StarBridge">
          <GitBranch size={22} />
        </div>
        {[Radar, Layers3, ShieldCheck, FileJson, Gauge].map((Icon, index) => (
          <a className="icon-button" key={index} href={['#bridges', '#recipes', '#evidence', '#resources', '#result'][index]}>
            <Icon size={18} />
          </a>
        ))}
      </aside>

      <section className="workbench-hero">
        <div className="hero-copy">
          <div className="status-pill">
            <span className={error ? 'is-offline' : ''} />
            {error ? 'Backend offline' : `Backend connected: ${API_BASE}`}
          </div>
          <h1>StarBridge Creative Workbench</h1>
          <p>
            面向 Photoshop、Blender、CAD 和 ComfyUI 的本地优先控制台：选择软件桥，选择已审查 recipe，预览计划和证据，再确认一次安全执行请求。
          </p>
        </div>

        <div className="backend-panel">
          <div className="panel-title">
            <Activity size={18} />
            <strong>Backend</strong>
            <button type="button" onClick={() => void loadBootstrap()} aria-label="Refresh backend">
              <RefreshCcw size={16} />
            </button>
          </div>
          <dl>
            <div>
              <dt>Tools</dt>
              <dd>{loading ? '...' : (payload?.capabilities.capability_count ?? 0)}</dd>
            </div>
            <div>
              <dt>Recipes</dt>
              <dd>{loading ? '...' : recipes.length}</dd>
            </div>
            <div>
              <dt>Catalog</dt>
              <dd>{loading ? '...' : catalogItems.length}</dd>
            </div>
            <div>
              <dt>Events</dt>
              <dd>{loading ? '...' : auditEvents.length}</dd>
            </div>
          </dl>
          {error ? <p className="error-text">{error}</p> : <p>HTTP API 已接入 MCP 安全工具层，执行动作会记录到本地审计历史。</p>}
        </div>
      </section>

      <section className="workspace-grid">
        <div className="panel bridge-panel" id="bridges">
          <div className="section-heading">
            <p>Capability Matrix</p>
            <h2>软件桥能力</h2>
          </div>
          <div className="bridge-list">
            {bridgeEntries.map(([bridge, overview]) => (
              <button
                className={`bridge-row ${bridge === activeBridge ? 'is-active' : ''}`}
                key={bridge}
                onClick={() => setActiveBridge(bridge)}
                style={{ '--accent': bridgeColors[bridge] ?? '#87f7ff' } as CSSProperties}
                type="button"
              >
                <span>{bridgeLabels[bridge] ?? bridge}</span>
                <strong>{overview.software}</strong>
                <em>{overview.safe_default_tool_count}/{overview.tool_count}</em>
              </button>
            ))}
          </div>
        </div>

        <article className="panel bridge-detail" style={{ '--accent': activeColor } as CSSProperties}>
          <div className="detail-top">
            <Sparkles size={22} />
            <span>{activeOverview?.statuses.join(' / ') || 'loading'}</span>
          </div>
          <h2>{activeOverview?.display_name ?? 'Loading bridge'}</h2>
          <p>{activeOverview?.safety_boundary ?? '正在读取后端能力边界。'}</p>
          <div className="fact-grid">
            <div>
              <LockKeyhole size={18} />
              <span>Safe tools</span>
              <strong>{activeOverview?.safe_default_tool_count ?? 0}</strong>
            </div>
            <div>
              <MonitorCog size={18} />
              <span>Guarded tools</span>
              <strong>{activeOverview?.guarded_tool_count ?? 0}</strong>
            </div>
          </div>
        </article>

        <div className="panel recipe-panel" id="recipes">
          <div className="section-heading">
            <p>Recipes</p>
            <h2>受审查工作流</h2>
          </div>
          <div className="recipe-list">
            {visibleRecipes.map((recipe) => (
              <button
                className={`recipe-row ${recipe.recipe_id === selectedRecipe ? 'is-selected' : ''}`}
                key={recipe.recipe_id}
                onClick={() => setSelectedRecipe(recipe.recipe_id)}
                type="button"
              >
                <strong>{recipe.recipe_id}</strong>
                <span>{recipe.bridge}</span>
              </button>
            ))}
            {!visibleRecipes.length && (
              <div className="empty-state">
                <strong>No reviewed recipe yet</strong>
                <span>Select another bridge or add a safe recipe in the backend registry.</span>
              </div>
            )}
          </div>
          <div className="action-row">
            <button disabled={!selectedRecipe || busyAction !== null} onClick={() => void runRecipeAction('plan')} type="button">
              <Play size={16} />
              Plan
            </button>
            <button disabled={!selectedRecipe || busyAction !== null} onClick={() => void runRecipeAction('evidence')} type="button">
              <FileJson size={16} />
              Evidence
            </button>
            <button
              disabled={!selectedRecipe || !confirmRun || !activeLane || busyAction !== null}
              onClick={() => void runRecipeAction('run')}
              type="button"
            >
              <TerminalSquare size={16} />
              Run
            </button>
          </div>
          <div className="run-confirm">
            <div>
              <strong>{activeCatalogItem?.title ?? selectedRecipe ?? 'No recipe selected'}</strong>
              <span>{activeCatalogItem?.price_signal ?? 'Select a reviewed recipe before execution.'}</span>
            </div>
            <div className="lane-picker" role="radiogroup" aria-label="Execution target">
              {supportedLanes.map((lane) => (
                <label key={lane.id}>
                  <input
                    checked={executionTarget === lane.execution_target}
                    name="execution_target"
                    onChange={() => setExecutionTarget(lane.execution_target)}
                    type="radio"
                  />
                  <span>{lane.execution_target}</span>
                </label>
              ))}
            </div>
            <label className="confirm-box">
              <input checked={confirmRun} onChange={(event) => setConfirmRun(event.target.checked)} type="checkbox" />
              <span>我已检查 Plan 和 Evidence，确认记录一次受控执行请求。</span>
            </label>
          </div>
        </div>

        <div className="panel safety-panel" id="evidence">
          <div className="section-heading">
            <p>Safety</p>
            <h2>执行前检查</h2>
          </div>
          {(payload?.capabilities.planner_hints.safe_discovery_sequence ?? []).map((step) => (
            <div className="check-item" key={step}>
              <CheckCircle2 size={17} />
              <span>{step}</span>
            </div>
          ))}
        </div>

        <div className="panel tiers-panel">
          <div className="section-heading">
            <p>Pricing Model</p>
            <h2>Free / Pro / Team 分层</h2>
          </div>
          <div className="tier-grid">
            {productTiers.map((tier) => (
              <article className="tier-card" key={tier.id}>
                <strong>{tier.name}</strong>
                <p>{tier.audience}</p>
                <span>{tier.included[0]}</span>
                <em>{tier.limits[0]}</em>
              </article>
            ))}
          </div>
        </div>

        <div className="panel hybrid-panel">
          <div className="section-heading">
            <p>Hybrid Runtime</p>
            <h2>本地 + 云执行通道</h2>
          </div>
          <p className="panel-note">{payload?.hybrid.policy ?? '正在读取混合执行策略。'}</p>
          <div className="lane-grid">
            {hybridLanes.map((lane) => (
              <article className={`lane-card ${activeLane?.id === lane.id ? 'is-active' : ''}`} key={lane.id}>
                <div>
                  <strong>{lane.label}</strong>
                  <span>{lane.execution_target}</span>
                </div>
                <p>{lane.safety}</p>
                <em>{lane.billing_unit}</em>
              </article>
            ))}
          </div>
        </div>

        <div className="panel catalog-panel">
          <div className="section-heading">
            <p>Recipe Store</p>
            <h2>可商品化工作流</h2>
          </div>
          <div className="catalog-grid">
            {visibleCatalogItems.map((item) => (
              <article className="catalog-card" key={item.sku}>
                <div>
                  <span>{item.tier}</span>
                  <em>{item.install_state}</em>
                </div>
                <h3>{item.title}</h3>
                <p>{item.goal}</p>
                <strong>{item.price_signal}</strong>
                <small>{item.buyer}</small>
              </article>
            ))}
          </div>
        </div>

        <div className="panel history-panel">
          <div className="section-heading with-action">
            <span>
              <p>Audit</p>
              <h2>执行历史</h2>
            </span>
            <button type="button" onClick={() => void clearAuditHistory()} disabled={!auditEvents.length}>
              Clear
            </button>
          </div>
          <div className="history-list">
            {auditEvents.map((event) => (
              <div className="history-row" key={event.event_id}>
                <span>{event.action}</span>
                <strong>{event.recipe_id}</strong>
                <em>{event.execution_target ? `${event.status} · ${event.execution_target}` : event.status}</em>
              </div>
            ))}
            {!auditEvents.length && (
              <div className="empty-state">
                <strong>No audit events yet</strong>
                <span>Run Plan or Evidence to create a local audit trail.</span>
              </div>
            )}
          </div>
        </div>

        <div className="panel resources-panel" id="resources">
          <div className="section-heading">
            <p>Resources</p>
            <h2>只读上下文</h2>
          </div>
          {(payload?.resources.resources ?? []).map((resource) => (
            <div className="resource-row" key={resource.uri}>
              <Boxes size={16} />
              <span>{resource.uri}</span>
              <em>{resource.mimeType}</em>
            </div>
          ))}
        </div>

        <div className="panel result-panel" id="result">
          <div className="section-heading">
            <p>Result</p>
            <h2>后端返回</h2>
          </div>
          <pre>{JSON.stringify(toolResult ?? { hint: '选择一个 recipe，然后点击 Plan 或 Evidence。' }, null, 2)}</pre>
        </div>
      </section>
    </main>
  );
}

export default App;
