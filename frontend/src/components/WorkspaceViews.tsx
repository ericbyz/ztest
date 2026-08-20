import {
  AlertTriangle,
  ArrowRight,
  Database,
  Download,
  GitFork,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type {
  OperationGraph,
  OperationGraphEdge,
  OperationItem,
  OperationRelationKind,
  RequirementItem,
  Run,
} from '../types'

export function RequirementsView({ requirements, onApprove, onAnalyze, onGenerate }: {
  requirements: RequirementItem[]
  onApprove: (id: string) => Promise<void>
  onAnalyze: () => Promise<void>
  onGenerate?: (recordIds: string[]) => Promise<void>
}) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const toggle = (recordId: string) => setSelected((current) => {
    const next = new Set(current)
    if (next.has(recordId)) next.delete(recordId)
    else next.add(recordId)
    return next
  })
  const toggleExpanded = (recordId: string) => setExpanded((current) => {
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
            <p className={expanded.has(item.record_id) ? 'expanded' : ''}>{item.text}</p>
            {item.text.length > 240 ? (
              <button
                aria-expanded={expanded.has(item.record_id)}
                className="requirement-detail-toggle"
                onClick={() => toggleExpanded(item.record_id)}
                type="button"
              >
                {expanded.has(item.record_id) ? '收起详情' : '展开详情'}
              </button>
            ) : null}
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

const RELATION_META: Record<OperationRelationKind, { label: string; basis: string }> = {
  scenario_flow: { label: '场景调用', basis: '明确关系' },
  schema_flow: { label: '字段数据流', basis: '推断关系' },
  resource_relation: { label: '资源关联', basis: '结构关系' },
}

type RelationFilter = OperationRelationKind | 'all'

interface GraphPosition {
  x: number
  y: number
}

export function ApiView({ graph }: { graph: OperationGraph }) {
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState('all')
  const [relationFilter, setRelationFilter] = useState<RelationFilter>('all')
  const [selectedId, setSelectedId] = useState(() => mostConnectedNode(graph))

  const nodeLookup = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes],
  )
  const filteredNodes = useMemo(() => {
    const term = search.trim().toLowerCase()
    return graph.nodes.filter((node) => {
      const groupMatches = group === 'all' || node.tags.includes(group)
      const searchMatches = !term || [node.id, node.path, node.summary, ...node.tags]
        .some((value) => value.toLowerCase().includes(term))
      return groupMatches && searchMatches
    })
  }, [graph.nodes, group, search])
  const filteredIds = useMemo(() => new Set(filteredNodes.map((node) => node.id)), [filteredNodes])
  const filteredEdges = useMemo(() => graph.edges.filter((edge) => (
    (relationFilter === 'all' || edge.kind === relationFilter)
    && filteredIds.has(edge.source)
    && filteredIds.has(edge.target)
  )), [filteredIds, graph.edges, relationFilter])
  const effectiveSelectedId = filteredIds.has(selectedId)
    ? selectedId
    : mostConnectedNode({ nodes: filteredNodes, edges: filteredEdges, groups: graph.groups })
  const selectedNode = nodeLookup.get(effectiveSelectedId)
  const neighborhoodEdges = filteredEdges
    .filter((edge) => edge.source === effectiveSelectedId || edge.target === effectiveSelectedId)
    .sort((left, right) => right.confidence - left.confidence)
    .slice(0, 12)
  const layout = useMemo(
    () => buildNeighborhoodLayout(effectiveSelectedId, neighborhoodEdges),
    [effectiveSelectedId, neighborhoodEdges],
  )

  return (
    <div className="workspace-view api-graph-view">
      <ViewHeader title="API 关系图谱" description="只展示带证据的场景调用、字段数据流和资源结构关系。" />
      {graph.nodes.length === 0 ? <EmptyCollection title="尚无 API Operation" description="在接入中心导入 OpenAPI、Swagger、Postman Collection 或 HAR。" /> : (
        <>
          <section className="api-graph-overview" aria-label="图谱统计">
            <GraphMetric icon={<Database size={17} />} label="API 节点" value={graph.nodes.length} />
            <GraphMetric icon={<GitFork size={17} />} label="证据关系" value={graph.edges.length} />
            <GraphMetric icon={<Network size={17} />} label="业务模块" value={graph.groups.length} />
            <div className="api-graph-principle"><ShieldCheck size={17} /><span><strong>证据优先</strong><small>没有来源依据的关系不会进入图谱</small></span></div>
          </section>

          <section className="api-graph-controls" aria-label="图谱筛选">
            <label className="api-graph-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 Operation、路径或说明" /></label>
            <label>模块<select value={group} onChange={(event) => setGroup(event.target.value)}><option value="all">全部模块</option>{graph.groups.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
            <label>焦点 API<select value={effectiveSelectedId} onChange={(event) => setSelectedId(event.target.value)}>{filteredNodes.map((node) => <option value={node.id} key={node.id}>{node.id}</option>)}</select></label>
            <div className="relation-filters" aria-label="关系类型">
              {(['all', 'scenario_flow', 'schema_flow', 'resource_relation'] as const).map((kind) => (
                <button className={relationFilter === kind ? 'active' : ''} onClick={() => setRelationFilter(kind)} type="button" key={kind}>{kind === 'all' ? '全部关系' : RELATION_META[kind].label}</button>
              ))}
            </div>
          </section>

          <div className="api-graph-legend">
            {(Object.keys(RELATION_META) as OperationRelationKind[]).map((kind) => <span className={`legend-${kind}`} key={kind}><i />{RELATION_META[kind].label}<small>{RELATION_META[kind].basis}</small></span>)}
          </div>

          <section className="api-graph-layout">
            <div className="api-graph-stage-shell">
              <header><div><GitFork size={17} /><strong>一跳关系视图</strong></div><span>聚焦单个 API，最多展示 12 条最强关系</span></header>
              {selectedNode && neighborhoodEdges.length > 0 ? (
                <div className="api-graph-stage" style={{ height: layout.height }}>
                  <svg aria-label={`${selectedNode.id} 的关系连线`} role="img" viewBox={`0 0 ${layout.width} ${layout.height}`} preserveAspectRatio="xMinYMin meet">
                    <defs>
                      <marker id="api-arrow-explicit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
                      <marker id="api-arrow-inferred" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
                    </defs>
                    {neighborhoodEdges.map((edge) => <GraphEdgePath edge={edge} positions={layout.positions} key={edge.id} />)}
                  </svg>
                  {[...layout.positions].map(([nodeId, position]) => {
                    const node = nodeLookup.get(nodeId)
                    if (!node) return null
                    return <GraphNodeButton node={node} position={position} selected={nodeId === effectiveSelectedId} onSelect={setSelectedId} key={nodeId} />
                  })}
                </div>
              ) : <GraphEmpty selectedNode={selectedNode} />}
            </div>

            <aside className="api-relation-inspector">
              <header><span>关系证据</span><strong>{selectedNode?.id ?? '未选择 API'}</strong></header>
              {selectedNode ? <div className="selected-operation"><div><span className={`method method-${selectedNode.method.toLowerCase()}`}>{selectedNode.method}</span><code>{selectedNode.path}</code></div><p>{selectedNode.summary || '未提供接口说明'}</p><small>{selectedNode.tags.join(' · ') || '未分组'} · 就绪度 {selectedNode.readiness}</small></div> : null}
              <div className="api-relation-list">
                {neighborhoodEdges.length === 0 ? <p className="api-relation-empty">当前筛选下没有与该 API 直接相连的证据关系。</p> : neighborhoodEdges.map((edge) => {
                  const incoming = edge.target === effectiveSelectedId
                  const neighbor = nodeLookup.get(incoming ? edge.source : edge.target)
                  return <article className={`relation-card relation-${edge.kind}`} key={edge.id}><div><span>{RELATION_META[edge.kind].label}</span><b>{edge.confidence}%</b></div><button onClick={() => neighbor && setSelectedId(neighbor.id)} type="button">{incoming ? '← ' : '→ '}{neighbor?.id ?? '未知节点'}</button><p>{edge.evidence}</p><small>{RELATION_META[edge.kind].basis}</small></article>
                })}
              </div>
            </aside>
          </section>
        </>
      )}
    </div>
  )
}

function GraphMetric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return <div className="api-graph-metric">{icon}<span><strong>{value}</strong><small>{label}</small></span></div>
}

function GraphEmpty({ selectedNode }: { selectedNode?: OperationItem }) {
  return <div className="api-graph-empty"><Network size={28} /><strong>当前没有可展示的真实关系</strong><p>{selectedNode ? `${selectedNode.id} 在当前筛选条件下没有带证据的一跳关系。` : '请调整搜索、模块或关系类型筛选。'}</p></div>
}

function GraphNodeButton({ node, position, selected, onSelect }: { node: OperationItem; position: GraphPosition; selected: boolean; onSelect: (id: string) => void }) {
  return <button className={`api-graph-node ${selected ? 'selected' : ''}`} style={{ left: position.x, top: position.y }} onClick={() => onSelect(node.id)} aria-pressed={selected} type="button"><div><span className={`method method-${node.method.toLowerCase()}`}>{node.method}</span><strong>{node.id}</strong></div><code>{node.path}</code><footer><span>{node.summary || '未提供说明'}</span><b>{node.readiness}</b></footer></button>
}

function GraphEdgePath({ edge, positions }: { edge: OperationGraphEdge; positions: Map<string, GraphPosition> }) {
  const source = positions.get(edge.source)
  const target = positions.get(edge.target)
  if (!source || !target) return null
  const sourceOnLeft = source.x < target.x
  const x1 = source.x + (sourceOnLeft ? 214 : 0)
  const x2 = target.x + (sourceOnLeft ? 0 : 214)
  const y1 = source.y + 47
  const y2 = target.y + 47
  const bend = x1 + (x2 - x1) / 2
  const routeOffset = edge.kind === 'scenario_flow' ? -16 : edge.kind === 'resource_relation' ? 16 : 0
  const marker = edge.kind === 'resource_relation' ? undefined : `url(#api-arrow-${edge.kind === 'scenario_flow' ? 'explicit' : 'inferred'})`
  return <g className={`api-graph-edge edge-${edge.kind}`}><title>{edge.label}：{edge.evidence}</title><path d={`M ${x1} ${y1} C ${bend} ${y1 + routeOffset}, ${bend} ${y2 + routeOffset}, ${x2} ${y2}`} markerEnd={marker} /><text x={bend} y={(y1 + y2) / 2 + routeOffset - 5}>{edge.label}</text></g>
}

function mostConnectedNode(graph: OperationGraph): string {
  const degree = new Map<string, number>()
  graph.edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1)
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1)
  })
  return graph.nodes.reduce((best, node) => (
    (degree.get(node.id) ?? 0) > (degree.get(best) ?? -1) ? node.id : best
  ), graph.nodes[0]?.id ?? '')
}

function buildNeighborhoodLayout(selectedId: string, edges: OperationGraphEdge[]) {
  const incoming = [...new Set(edges.filter((edge) => edge.target === selectedId).map((edge) => edge.source))]
  const outgoing = [...new Set(edges.filter((edge) => edge.source === selectedId).map((edge) => edge.target).filter((id) => !incoming.includes(id)))]
  const rows = Math.max(incoming.length, outgoing.length, 1)
  const height = Math.max(430, rows * 116 + 76)
  const positions = new Map<string, GraphPosition>([[selectedId, { x: 383, y: height / 2 - 47 }]])
  const placeColumn = (ids: string[], x: number) => {
    const total = (ids.length - 1) * 116
    ids.forEach((id, index) => positions.set(id, { x, y: height / 2 - total / 2 - 47 + index * 116 }))
  }
  placeColumn(incoming, 34)
  placeColumn(outgoing, 732)
  return { width: 980, height, positions }
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
