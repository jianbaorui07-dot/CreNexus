const CAPABILITIES = [
  ["原生可编辑", ".drawio + 内嵌 XML 的 SVG，不把结构压平成一次性图片"],
  ["稳定局部修改", "使用语义稳定 ID，只更新指定元素，并校验其他区域哈希"],
  ["结构质量门", "检查 XML、连接端点、越界、重叠、文字裁切风险和对比度"],
  ["可续跑批任务", "确定性任务 ID、幂等文档哈希、并发上限和完成项续跑"],
] as const;

export function DiagramForgePage() {
  return (
    <div className="standard-page diagramforge-page">
      <header className="page-intro">
        <div>
          <span className="page-kicker">结构化绘图 · HEADLESS READY</span>
          <h2>图枢 DiagramForge</h2>
          <p>
            面向科研框架、流程图、系统架构、网络拓扑、UML、BPMN 和复杂关系图。
            Canvas 继续负责自由构思；DiagramForge 负责可编辑结构、精确连接和可复核交付。
          </p>
        </div>
        <span className="local-badge">LOCAL / SAFE ROOTS</span>
      </header>

      <section className="workspace-card">
        <div className="section-heading">
          <div>
            <span>CORE</span>
            <h3>独立的结构化绘图工作台</h3>
          </div>
        </div>
        <div className="integration-grid">
          {CAPABILITIES.map(([title, body]) => (
            <article key={title}>
              <span className="integration-mark">Df</span>
              <div>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="workspace-card">
        <div className="section-heading">
          <div>
            <span>QUICK START</span>
            <h3>先规划，再确认写入</h3>
          </div>
        </div>
        <div className="diagnostic-command-grid">
          <code>npm.cmd run drawio:probe</code>
          <code>npm.cmd run drawio:capabilities</code>
          <code>npm.cmd run drawio:plan</code>
          <code>python examples/drawio_bridge/cli.py demo --confirm-write</code>
        </div>
        <p className="truth-note">
          Headless 编译器、Draw.io Desktop 和 Live MCP 是三个独立状态。PDF 需要本机 Draw.io Desktop；
          实时画布需要外部适配器，未连接时不会显示为已连接。
        </p>
      </section>
    </div>
  );
}
