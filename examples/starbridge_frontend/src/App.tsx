import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import {
  Activity,
  Boxes,
  CheckCircle2,
  Code2,
  Download,
  Eye,
  FileJson,
  Gauge,
  GitBranch,
  Layers3,
  LockKeyhole,
  MonitorCog,
  Play,
  Radar,
  ShieldCheck,
  TerminalSquare,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import * as THREE from 'three';

type Bridge = {
  id: string;
  name: string;
  label: string;
  state: 'stable' | 'experimental' | 'planned' | 'research';
  summary: string;
  safeDefault: string;
  command: string;
  color: string;
};

const bridges: Bridge[] = [
  {
    id: '01',
    name: 'ComfyUI',
    label: 'workflow 验证',
    state: 'stable',
    summary: '校验 workflow JSON，离线时仍返回安全状态，不暴露本机模型和生成图。',
    safeDefault: '只读 probe / workflow validate',
    command: 'npm.cmd run comfy:probe',
    color: '#00d7ff',
  },
  {
    id: '02',
    name: 'Blender',
    label: '场景桥接',
    state: 'planned',
    summary: '先做环境探针和场景证据规划，公开仓库不读取私有 blend 和贴图资产。',
    safeDefault: '环境摘要 / 未来 evidence',
    command: 'python examples\\bridge_status.py --probe-executables',
    color: '#f2c94c',
  },
  {
    id: '03',
    name: 'AutoCAD / DXF',
    label: '工程图 dry-run',
    state: 'stable',
    summary: '把自然语言或 JSON plan 转成可审查 DXF 结构，写入必须显式确认。',
    safeDefault: 'dry-run 默认开启',
    command: 'python examples\\cad\\generate_dxf_plan.py',
    color: '#7cf29a',
  },
  {
    id: '04',
    name: 'Photoshop',
    label: '沙盒演示',
    state: 'experimental',
    summary: '仅做授权本机软件的 sandbox demo 和脱敏文档摘要，不默认打开 PSD。',
    safeDefault: '参数化输入输出',
    command: 'npm.cmd run photoshop:demo:plan',
    color: '#3ea2ff',
  },
  {
    id: '05',
    name: 'Illustrator',
    label: '矢量导出',
    state: 'experimental',
    summary: '面向 .ai / SVG / PDF / PNG 的可控导出研究，真实写入限制在示例输出。',
    safeDefault: 'sandbox export plan',
    command: 'npm.cmd run illustrator:demo:plan',
    color: '#ff8a3d',
  },
  {
    id: '06',
    name: 'CapCut / 剪映',
    label: '草稿探针',
    state: 'research',
    summary: '只检查可执行文件和配置可用性，不递归读取用户真实草稿内容。',
    safeDefault: 'draft path probe only',
    command: 'npm.cmd run bridge:status:safe',
    color: '#d892ff',
  },
];

const stateLabel: Record<Bridge['state'], string> = {
  stable: 'Stable',
  experimental: 'Experimental',
  planned: 'Planned',
  research: 'Research',
};

const checks = [
  ['redact-paths', '真实路径脱敏'],
  ['dry-run', '写入默认只计划'],
  ['safe-only', '工具列表可过滤'],
  ['soft-exit', '离线不阻塞展示'],
  ['sandbox', '输出限制在示例目录'],
];

const metrics: Array<{ value: string; label: string; Icon: LucideIcon }> = [
  { value: 'v0.1-alpha', label: '当前阶段', Icon: Activity },
  { value: '6 bridges', label: '软件桥数量', Icon: Layers3 },
  { value: 'dry-run', label: '写入默认策略', Icon: Play },
  { value: 'redacted', label: '路径输出策略', Icon: Eye },
  { value: 'local only', label: '私有资产边界', Icon: Download },
];

function Starfield({ activeBridge }: { activeBridge: Bridge }) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 900);
    camera.position.set(0, 8, 48);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const count = 9000;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const bridgeColor = new THREE.Color(activeBridge.color);
    const baseColor = new THREE.Color('#86f7ff');

    for (let index = 0; index < count; index += 1) {
      const stride = index * 3;
      const ring = index % bridges.length;
      const radius = 5 + (index % 140) * 0.13;
      const angle = index * 0.047 + ring * 0.8;
      const layer = Math.floor(index / 140) % 18;

      positions[stride] = Math.cos(angle) * radius;
      positions[stride + 1] = Math.sin(layer * 0.7) * 5 + (Math.random() - 0.5) * 8;
      positions[stride + 2] = Math.sin(angle) * radius + (layer - 9) * 1.8;

      const mix = ring === Number(activeBridge.id) - 1 ? 0.85 : 0.25;
      const color = baseColor.clone().lerp(bridgeColor, mix);
      colors[stride] = color.r;
      colors[stride + 1] = color.g;
      colors[stride + 2] = color.b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.08,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);

    const arcs = new THREE.Group();
    bridges.forEach((bridge, index) => {
      const curve = new THREE.EllipseCurve(0, 0, 10 + index * 3.2, 10 + index * 3.2, 0, Math.PI * 1.55);
      const curvePoints = curve.getPoints(96).map((point) => new THREE.Vector3(point.x, (index - 2.5) * 2, point.y));
      const lineGeometry = new THREE.BufferGeometry().setFromPoints(curvePoints);
      const line = new THREE.Line(
        lineGeometry,
        new THREE.LineBasicMaterial({
          color: bridge.color,
          transparent: true,
          opacity: bridge.id === activeBridge.id ? 0.75 : 0.18,
        }),
      );
      line.rotation.x = Math.PI * 0.62;
      arcs.add(line);
    });
    scene.add(arcs);

    let raf = 0;
    const resize = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const animate = () => {
      raf = requestAnimationFrame(animate);
      const time = performance.now() * 0.00018;
      points.rotation.y = time;
      points.rotation.x = Math.sin(time * 1.7) * 0.08;
      arcs.rotation.y = -time * 1.35;
      renderer.render(scene, camera);
    };

    resize();
    animate();
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      container.removeChild(renderer.domElement);
      geometry.dispose();
      material.dispose();
      arcs.children.forEach((child) => {
        const line = child as THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>;
        line.geometry.dispose();
        line.material.dispose();
      });
      renderer.dispose();
    };
  }, [activeBridge]);

  return <div className="starfield" ref={mountRef} aria-hidden="true" />;
}

function App() {
  const [activeId, setActiveId] = useState('01');
  const activeBridge = useMemo(() => bridges.find((bridge) => bridge.id === activeId) ?? bridges[0], [activeId]);

  return (
    <main className="app-shell">
      <Starfield activeBridge={activeBridge} />
      <div className="mesh-overlay" />

      <aside className="side-rail" aria-label="StarBridge navigation">
        <div className="rail-mark">
          <GitBranch size={22} />
        </div>
        {[MonitorCog, Boxes, ShieldCheck, FileJson, Gauge].map((Icon, index) => (
          <button className="icon-button" key={index} type="button" aria-label={`导航 ${index + 1}`}>
            <Icon size={18} />
          </button>
        ))}
      </aside>

      <section className="hero-panel">
        <div className="hero-copy">
          <div className="status-pill">
            <span />
            Windows-first / Local-first / Safety Verification Layer
          </div>
          <h1>StarBridge Creative Console</h1>
          <p>
            面向 Codex 接入本地创作软件的公开前端：把 ComfyUI、Blender、AutoCAD、Photoshop、
            Illustrator 和剪映能力拆成可验证的状态、dry-run 计划、脱敏证据与安全边界。
          </p>
          <div className="hero-actions">
            <a className="button primary" href="#matrix">
              <Radar size={17} />
              查看能力矩阵
            </a>
            <a className="button secondary" href="#commands">
              <TerminalSquare size={17} />
              本地验证命令
            </a>
          </div>
        </div>

        <div className="command-panel" id="commands">
          <div className="panel-head">
            <span />
            <span />
            <span />
            <strong>safe-preflight</strong>
          </div>
          <pre>{`npm.cmd run bridge:status:safe
npm.cmd run starbridge:tools:safe
python scripts\\security_check.py
python scripts\\starbridge_preflight.py --markdown`}</pre>
        </div>
      </section>

      <section className="dashboard-grid" id="matrix">
        <div className="matrix-panel">
          <div className="section-heading">
            <p>Capability Matrix</p>
            <h2>六条软件桥，按真实能力分层展示</h2>
          </div>
          <div className="bridge-list">
            {bridges.map((bridge) => (
              <button
                className={`bridge-row ${bridge.id === activeId ? 'is-active' : ''}`}
                key={bridge.id}
                onClick={() => setActiveId(bridge.id)}
                type="button"
                style={{ '--accent': bridge.color } as CSSProperties}
              >
                <span className="bridge-id">{bridge.id}</span>
                <span>
                  <strong>{bridge.name}</strong>
                  <small>{bridge.label}</small>
                </span>
                <em>{stateLabel[bridge.state]}</em>
              </button>
            ))}
          </div>
        </div>

        <article className="detail-panel" style={{ '--accent': activeBridge.color } as CSSProperties}>
          <div className="detail-top">
            <span>{activeBridge.id}</span>
            <em>{stateLabel[activeBridge.state]}</em>
          </div>
          <h2>{activeBridge.name}</h2>
          <p>{activeBridge.summary}</p>
          <div className="detail-facts">
            <div>
              <LockKeyhole size={18} />
              <span>安全默认</span>
              <strong>{activeBridge.safeDefault}</strong>
            </div>
            <div>
              <Code2 size={18} />
              <span>验证入口</span>
              <strong>{activeBridge.command}</strong>
            </div>
          </div>
        </article>

        <div className="evidence-panel">
          <div className="section-heading">
            <p>Evidence</p>
            <h2>发布前必须能说明风险边界</h2>
          </div>
          <div className="check-grid">
            {checks.map(([key, label]) => (
              <div className="check-item" key={key}>
                <CheckCircle2 size={18} />
                <span>{key}</span>
                <strong>{label}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="pipeline-panel">
          <div className="section-heading">
            <p>Workflow</p>
            <h2>从请求到 PR 的公开安全链路</h2>
          </div>
          {['确认属于公开接入范围', '过滤真实路径和私有资产', '默认 dry-run 或只读探针', '生成证据 manifest', '运行安全扫描和测试'].map(
            (step, index) => (
              <div className="pipeline-step" key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
              </div>
            ),
          )}
        </div>
      </section>

      <section className="metrics-strip" aria-label="project metrics">
        {metrics.map(({ value, label, Icon }) => (
          <div className="metric" key={label}>
            <Icon size={19} />
            <strong>{value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </section>
    </main>
  );
}

export default App;
