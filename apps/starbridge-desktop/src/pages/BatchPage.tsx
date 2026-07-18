export function BatchPage() {
  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">专业版规划中</span><h2>生产级批量工作流</h2><p>批量队列、文件夹处理和可恢复任务属于未来新的私有 Pro 能力；当前公开构建没有这些实现。</p></div></header>
      <div className="locked-grid">
        {[['批量队列','统一安排多个本机任务并控制并发。'],['文件夹批处理','明确选择文件夹后按规则处理，不扫描其他目录。'],['可恢复任务','意外关闭后从安全检查点继续。'],['商业预设','保存团队参数与交付规范。']].map(([title, description]) => <article className="locked-card" key={title}><span className="lock-icon" aria-hidden="true">◇</span><span className="planned-label">尚未开放</span><h3>{title}</h3><p>{description}</p></article>)}
      </div>
      <p className="truth-note"><strong>当前状态：</strong>仅展示产品边界，没有伪造队列、输出或 Pro 功能代码。</p>
    </div>
  );
}
