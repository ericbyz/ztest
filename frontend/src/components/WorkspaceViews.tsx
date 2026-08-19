import {
  AlertTriangle,
  ArrowRight,
  Download,
  GitFork,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { OperationItem, RequirementItem, Run } from '../types'

export function RequirementsView({ requirements, onApprove, onAnalyze, onGenerate }: {
  requirements: RequirementItem[]
  onApprove: (id: string) => Promise<void>
  onAnalyze: () => Promise<void>
  onGenerate?: (recordIds: string[]) => Promise<void>
}) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const toggle = (recordId: string) => setSelected((current) => {
    const next = new Set(current)
    if (next.has(recordId)) next.delete(recordId)
    else next.add(recordId)
    return next
  })
  return (
    <div className="workspace-view">
      <ViewHeader title="需求中心" description="审核原子需求、业务规则、歧义和接口映射。" action={(
        <><button className="button secondary" onClick={() => void onAnalyze()} type="button"><Sparkles size={16} /> 分析与映射</button>{onGenerate ? <button className="button primary" disabled={selected.size === 0} onClick={() => void onGenerate([...selected])} type="button">生成场景（{selected.size}）</button> : null}</>
      )} />
      {requirements.length === 0 ? <EmptyCollection title="尚无结构化需求" description="先在接入中心选择文件、TAPD 或知识库来源。" /> : null}
      <div className="requirements-layout">
        {requirements.map((item) => (
          <article className={`requirement-card ${selected.has(item.record_id) ? 'selected' : ''}`} key={item.record_id}>
            <div className="requirement-top">
              <div><input aria-label={`选择 ${item.id}`} type="checkbox" checked={selected.has(item.record_id)} onChange={() => toggle(item.record_id)} /><span className="requirement-id">{item.id}</span><span className="priority">{item.priority}</span></div>
              <span className={`review-state ${item.status}`}>{item.status === 'approved' ? '已审核' : '待审核'}</span>
            </div>
            <h3>{item.title}</h3>
            <p>{item.text}</p>
            <div className="trace-source">来源 {item.source} · 置信度 {Math.round(item.confidence * 100)}%</div>
            {item.ambiguities.map((ambiguity) => <div className="ambiguity" key={ambiguity}><AlertTriangle size={14} /> {ambiguity}</div>)}
            <div className="mapping-row">
              {item.mapped_operations.slice(0, 3).map((mapping) => (
                <span key={mapping.operation_id}>{mapping.operation_id} <small>{Math.round(mapping.confidence * 100)}%</small></span>
              ))}
            </div>
            <div className="card-footer">
              <span>{item.business_rules.length} 条业务规则</span>
              {item.status !== 'approved' ? <button className="link-button" onClick={() => void onApprove(item.record_id)} type="button">确认需求 <ArrowRight size={14} /></button> : <span className="verified"><ShieldCheck size={14} /> 已锁定需求断言</span>}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

export function ApiView({ operations }: { operations: OperationItem[] }) {
  return (
    <div className="workspace-view">
      <ViewHeader title="API 图谱" description="Operation 目录、就绪度和 Producer—Consumer 依赖。" />
      {operations.length === 0 ? <EmptyCollection title="尚无 API Operation" description="在接入中心导入 OpenAPI、Swagger、Postman Collection 或 HAR。" /> : null}
      <section className="graph-surface">
        <div className="graph-header"><GitFork size={18} /> API Operation 关系视图 <span>{operations.length} Operations</span></div>
        <div className="api-nodes">
          {operations.map((operation, index) => (
            <div className="api-node-wrap" key={operation.id}>
              <article className="api-node">
                <div><span className={`method method-${operation.method.toLowerCase()}`}>{operation.method}</span><strong>{operation.id}</strong></div>
                <p>{operation.path}</p>
                <footer><span>{operation.summary}</span><b>{operation.readiness}</b></footer>
              </article>
              {index < operations.length - 1 ? <ArrowRight size={18} className="api-arrow" /> : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

export function ReportsView({ runs, projectId, onSelect }: { runs: Run[]; projectId: string; onSelect: (run: Run) => void }) {
  return (
    <div className="workspace-view">
      <ViewHeader title="执行与报告" description="分类失败、检查证据并导出稳定回归资产。" action={(
        <a className="button primary" href={`/api/projects/${projectId}/exports`}><Download size={16} /> 导出 pytest</a>
      )} />
      {runs.length === 0 ? <EmptyCollection title="尚无执行记录" description="生成场景并完成首次执行后，报告和证据会显示在这里。" /> : null}
      <div className="report-grid">
        {runs.map((run) => (
          <button className="report-card" onClick={() => onSelect(run)} key={run.id} type="button">
            <div className={`run-orb ${run.status}`}><span>{run.pass_rate}</span>%</div>
            <div><h3>{run.scenario_name}</h3><p>{new Date(run.started_at).toLocaleString('zh-CN')} · {run.environment}</p></div>
            <span className={`status ${run.status}`}>{run.status === 'passed' ? '通过' : '失败'}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function ViewHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <header className="view-header"><div><h1>{title}</h1><p>{description}</p></div>{action ? <div className="view-actions">{action}</div> : null}</header>
}

function EmptyCollection({ title, description }: { title: string; description: string }) {
  return <div className="empty-collection"><strong>{title}</strong><p>{description}</p></div>
}
