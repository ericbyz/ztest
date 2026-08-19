import {
  AlertTriangle, Bell, CheckCircle2, CircleHelp, FileCode2, FileText,
  GitFork, Layers3, Menu, Plus, Settings2, X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { CoverageRadar } from './components/CoverageRadar'
import { Metrics } from './components/Metrics'
import { EnvironmentModal, EmptyWorkspace, ProjectModal } from './components/Onboarding'
import { RunsTable } from './components/RunsTable'
import { Sidebar } from './components/Sidebar'
import { WorkflowEditor } from './components/WorkflowEditor'
import { ApiView, DocumentsView, ReportsView, RequirementsView } from './components/WorkspaceViews'
import type { Dashboard, DocumentItem, EnvironmentItem, NavKey, OperationItem, Project, RequirementItem, Run, Scenario } from './types'

interface ProjectData {
  documents: DocumentItem[]
  requirements: RequirementItem[]
  operations: OperationItem[]
  scenarios: Scenario[]
  environments: EnvironmentItem[]
}

const EMPTY_DATA: ProjectData = { documents: [], requirements: [], operations: [], scenarios: [], environments: [] }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProjectId, setActiveProjectId] = useState('')
  const [nav, setNav] = useState<NavKey>('overview')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [data, setData] = useState<ProjectData>(EMPTY_DATA)
  const [selectedScenarioId, setSelectedScenarioId] = useState('')
  const [environmentId, setEnvironmentId] = useState('')
  const [runMode, setRunMode] = useState<'simulated' | 'live'>('simulated')
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [projectModalOpen, setProjectModalOpen] = useState(false)
  const [environmentModalOpen, setEnvironmentModalOpen] = useState(false)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const loadProject = useCallback(async (projectId: string) => {
    setLoading(true)
    try {
      const [dashboardResult, documents, requirements, operations, scenarios, environments] = await Promise.all([
        api.dashboard(projectId), api.documents(projectId), api.requirements(projectId),
        api.operations(projectId), api.scenarios(projectId), api.environments(projectId),
      ])
      setActiveProjectId(projectId)
      setDashboard(dashboardResult)
      setData({ documents, requirements, operations, scenarios, environments })
      setSelectedScenarioId((current) => scenarios.some((item) => item.id === current) ? current : scenarios[0]?.id ?? '')
      setEnvironmentId((current) => environments.some((item) => item.id === current) ? current : environments.find((item) => item.is_default)?.id ?? environments[0]?.id ?? '')
    } catch (error) {
      setToast(error instanceof Error ? error.message : '加载项目失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const bootstrap = useCallback(async () => {
    setLoading(true)
    try {
      const projectRows = await api.projects()
      setProjects(projectRows)
      if (projectRows.length > 0) await loadProject(projectRows[0].id)
      else setLoading(false)
    } catch (error) {
      setLoading(false)
      setToast(error instanceof Error ? error.message : '连接后端失败')
    }
  }, [loadProject])

  useEffect(() => {
    // Initial API synchronization is intentionally owned by this mount effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void bootstrap()
  }, [bootstrap])

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(null), 3800)
    return () => window.clearTimeout(timer)
  }, [toast])

  const activeScenario = useMemo(
    () => data.scenarios.find((item) => item.id === selectedScenarioId) ?? data.scenarios[0] ?? null,
    [data.scenarios, selectedScenarioId],
  )

  const createProject = async (payload: { name: string; description: string; default_environment: string }) => {
    const project = await api.createProject(payload)
    setProjects(await api.projects())
    setProjectModalOpen(false)
    await loadProject(project.id)
    setToast('项目已创建。请导入需求文档和 OpenAPI。')
  }

  const refreshProject = async () => { if (activeProjectId) await loadProject(activeProjectId) }

  const upload = async (kind: 'requirement' | 'openapi', file: File) => {
    if (!activeProjectId) return
    try {
      await api.uploadDocument(activeProjectId, kind, file)
      await refreshProject()
      setToast(`${file.name} 已完成版本化保存与解析`)
    } catch (error) { setToast(error instanceof Error ? error.message : '上传失败') }
  }

  const analyze = async () => {
    if (!activeProjectId) return
    try {
      const result = await api.analyze(activeProjectId)
      await refreshProject()
      setToast(`已映射 ${result.requirements} 条需求与 ${result.operations} 个 Operation`)
    } catch (error) { setToast(error instanceof Error ? error.message : '分析失败') }
  }

  const generateScenario = async (recordIds: string[]) => {
    if (!activeProjectId) return
    try {
      const scenario = await api.generateScenario(activeProjectId, recordIds)
      await refreshProject()
      setSelectedScenarioId(scenario.id)
      setNav('scenarios')
      setToast(scenario.validation_errors.length ? `场景已生成，存在 ${scenario.validation_errors.length} 个待修复校验问题` : '场景已生成并通过静态校验')
    } catch (error) { setToast(error instanceof Error ? error.message : '场景生成失败') }
  }

  const approveRequirement = async (recordId: string) => {
    const updated = await api.updateRequirement(recordId, 'approved')
    setData((current) => ({ ...current, requirements: current.requirements.map((item) => item.record_id === recordId ? updated : item) }))
    setToast(`${updated.id} 已确认，需求断言进入保护状态`)
  }

  const saveScenario = async (ir: Scenario['ir']) => {
    if (!activeScenario) return
    try {
      const updated = await api.updateScenario(activeScenario.id, ir)
      setData((current) => ({ ...current, scenarios: current.scenarios.map((item) => item.id === updated.id ? updated : item) }))
      setToast('Test IR 已保存并重新通过静态校验')
    } catch (error) {
      setToast(error instanceof Error ? error.message : '保存失败')
      throw error
    }
  }

  const approveScenario = async () => {
    if (!activeScenario) return
    try {
      const updated = await api.approveScenario(activeScenario.id)
      setData((current) => ({ ...current, scenarios: current.scenarios.map((item) => item.id === updated.id ? updated : item) }))
      setToast('场景已审核，可作为回归资产导出')
    } catch (error) { setToast(error instanceof Error ? error.message : '提交评审失败') }
  }

  const runScenario = async () => {
    if (!activeScenario) return
    setRunning(true)
    try {
      const run = await api.runScenario(activeScenario.id, environmentId || undefined, runMode)
      setSelectedRun(run)
      await refreshProject()
      setToast(`执行${run.status === 'passed' ? '通过' : '失败'}，通过率 ${run.pass_rate}%`)
    } catch (error) { setToast(error instanceof Error ? error.message : '执行失败') }
    finally { setRunning(false) }
  }

  const createEnvironment = async (payload: Omit<EnvironmentItem, 'id' | 'project_id' | 'created_at'>) => {
    if (!activeProjectId) return
    const environment = await api.createEnvironment(activeProjectId, payload)
    const environments = await api.environments(activeProjectId)
    setData((current) => ({ ...current, environments }))
    setEnvironmentId(environment.id)
    setToast('环境已保存；Secret 仍只存在于操作系统环境变量中')
  }

  if (loading) return <div className="loading-screen"><div className="loading-mark">AI</div><p>正在加载测试工作区…</p></div>
  if (!dashboard) return <><EmptyWorkspace onCreate={() => setProjectModalOpen(true)} />{projectModalOpen ? <ProjectModal onClose={() => setProjectModalOpen(false)} onCreate={createProject} /> : null}{toast ? <Toast message={toast} /> : null}</>

  return (
    <div className="app-shell">
      <Sidebar active={nav} onNavigate={setNav} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="app-main">
        <header className="topbar">
          <div className="project-switcher">
            <button className="mobile-menu" onClick={() => setSidebarOpen(true)} type="button"><Menu size={20} /></button>
            <span className="project-icon"><Layers3 size={18} /></span>
            <select aria-label="当前项目" value={activeProjectId} onChange={(event) => void loadProject(event.target.value)}>{projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select>
            <button className="icon-button add-project" onClick={() => setProjectModalOpen(true)} aria-label="创建项目" type="button"><Plus size={17} /></button>
          </div>
          <div className="topbar-actions">
            <label className="environment-select"><Layers3 size={16} /><select aria-label="执行环境" value={environmentId} onChange={(event) => setEnvironmentId(event.target.value)}>{data.environments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
            <button className="icon-button" onClick={() => setEnvironmentModalOpen(true)} type="button" aria-label="环境配置"><Settings2 size={18} /></button>
            <button className="icon-button" type="button" aria-label="帮助"><CircleHelp size={19} /></button>
            <button className="icon-button notification" type="button" aria-label="通知"><Bell size={19} />{dashboard.metrics.pending_reviews > 0 ? <span>{dashboard.metrics.pending_reviews}</span> : null}</button>
            <button className="button primary create-button" onClick={() => setNav('requirements')} type="button">生成测试场景 <Plus size={17} /></button>
          </div>
        </header>
        <main className="page-content">
          {nav === 'overview' ? <Overview dashboard={dashboard} data={data} onNavigate={setNav} onSelectRun={setSelectedRun} activeScenario={activeScenario} running={running} runMode={runMode} onModeChange={setRunMode} onRun={runScenario} onApprove={approveScenario} onSave={saveScenario} /> : null}
          {nav === 'documents' ? <DocumentsView documents={data.documents} onUpload={upload} /> : null}
          {nav === 'requirements' ? <RequirementsView requirements={data.requirements} onApprove={approveRequirement} onAnalyze={analyze} onGenerate={generateScenario} /> : null}
          {nav === 'api' ? <ApiView operations={data.operations} /> : null}
          {nav === 'scenarios' ? <ScenarioWorkspace scenarios={data.scenarios} activeScenario={activeScenario} selectedId={selectedScenarioId} onSelect={setSelectedScenarioId} running={running} runMode={runMode} onModeChange={setRunMode} onRun={runScenario} onApprove={approveScenario} onSave={saveScenario} onNavigate={setNav} /> : null}
          {nav === 'reports' ? <ReportsView runs={dashboard.recent_runs} projectId={dashboard.project.id} onSelect={setSelectedRun} /> : null}
        </main>
      </div>
      {selectedRun ? <RunDrawer run={selectedRun} onClose={() => setSelectedRun(null)} /> : null}
      {projectModalOpen ? <ProjectModal onClose={() => setProjectModalOpen(false)} onCreate={createProject} /> : null}
      {environmentModalOpen ? <EnvironmentModal project={dashboard.project} environments={data.environments} onClose={() => setEnvironmentModalOpen(false)} onCreate={createEnvironment} /> : null}
      {toast ? <Toast message={toast} /> : null}
    </div>
  )
}

interface OverviewProps {
  dashboard: Dashboard; data: ProjectData; onNavigate: (key: NavKey) => void
  onSelectRun: (run: Run) => void; activeScenario: Scenario | null; running: boolean
  runMode: 'simulated' | 'live'; onModeChange: (mode: 'simulated' | 'live') => void
  onRun: () => Promise<void>; onApprove: () => Promise<void>; onSave: (ir: Scenario['ir']) => Promise<void>
}

function Overview({ dashboard, data, onNavigate, onSelectRun, activeScenario, running, runMode, onModeChange, onRun, onApprove, onSave }: OverviewProps) {
  const hasInputs = data.documents.length > 0
  return <>
    <header className="page-heading"><div><h1>项目总览</h1><p>{dashboard.project.description || '尚未填写项目描述'}</p></div></header>
    <Metrics values={dashboard.metrics} />
    {!hasInputs ? <GettingStarted onNavigate={onNavigate} /> : null}
    {hasInputs ? <>
      <div className="overview-grid"><RunsTable runs={dashboard.recent_runs} onSelect={onSelectRun} />{dashboard.coverage.length ? <CoverageRadar data={dashboard.coverage} /> : <div className="panel empty-chart"><GitFork size={28} /><strong>等待生成覆盖数据</strong><p>完成需求映射与场景生成后显示模块覆盖率。</p></div>}</div>
      <div className="insight-row">
        {dashboard.warnings.length ? <section className="warning-band"><div className="warning-icon"><AlertTriangle size={20} /></div><div><h3>{dashboard.warnings[0].title}</h3><p>{dashboard.warnings[0].message}</p></div><button className="link-button" onClick={() => onNavigate('api')} type="button">查看详情</button></section> : <section className="warning-band healthy"><div className="warning-icon"><CheckCircle2 size={20} /></div><div><h3>当前无高优先级治理告警</h3><p>静态引用、清理策略和 API 就绪度未发现阻断问题。</p></div></section>}
        <section className="review-panel"><div className="review-title"><h3>待审核项</h3><button className="link-button" onClick={() => onNavigate('requirements')} type="button">查看全部</button></div>{dashboard.pending_reviews.map((item) => <div className="review-row" key={item.label}><span>{item.label}</span><b>{item.count}</b></div>)}</section>
      </div>
      {activeScenario ? <WorkflowEditor key={activeScenario.id} scenario={activeScenario} running={running} mode={runMode} onModeChange={onModeChange} onRun={() => void onRun()} onApprove={() => void onApprove()} onSave={onSave} /> : null}
    </> : null}
  </>
}

function GettingStarted({ onNavigate }: { onNavigate: (key: NavKey) => void }) {
  return <section className="getting-started"><header><div><h2>建立第一个测试闭环</h2><p>当前项目是空白工作区，不包含任何演示业务或虚构接口。</p></div><span>0 / 3</span></header><div className="setup-actions"><button onClick={() => onNavigate('documents')} type="button"><FileText size={22} /><div><strong>1. 上传需求文档</strong><p>支持 Markdown、TXT、DOCX</p></div><Plus size={16} /></button><button onClick={() => onNavigate('documents')} type="button"><FileCode2 size={22} /><div><strong>2. 导入 OpenAPI</strong><p>支持 3.0 / 3.1 JSON、YAML</p></div><Plus size={16} /></button><button onClick={() => onNavigate('requirements')} type="button"><GitFork size={22} /><div><strong>3. 分析并生成场景</strong><p>审核映射、断言和清理计划</p></div><Plus size={16} /></button></div></section>
}

interface ScenarioWorkspaceProps {
  scenarios: Scenario[]; activeScenario: Scenario | null; selectedId: string; onSelect: (id: string) => void
  running: boolean; runMode: 'simulated' | 'live'; onModeChange: (mode: 'simulated' | 'live') => void
  onRun: () => Promise<void>; onApprove: () => Promise<void>; onSave: (ir: Scenario['ir']) => Promise<void>; onNavigate: (key: NavKey) => void
}

function ScenarioWorkspace({ scenarios, activeScenario, selectedId, onSelect, running, runMode, onModeChange, onRun, onApprove, onSave, onNavigate }: ScenarioWorkspaceProps) {
  return <div className="workspace-view editor-only"><header className="view-header"><div><h1>场景编辑器</h1><p>选择任意生成场景，以流程或 Test IR 视图编辑、校验和执行。</p></div>{scenarios.length ? <select className="scenario-select" value={selectedId} onChange={(event) => onSelect(event.target.value)}>{scenarios.map((item) => <option value={item.id} key={item.id}>{item.name} · v{item.version}</option>)}</select> : null}</header>{activeScenario ? <WorkflowEditor key={activeScenario.id} scenario={activeScenario} running={running} mode={runMode} onModeChange={onModeChange} onRun={() => void onRun()} onApprove={() => void onApprove()} onSave={onSave} /> : <div className="empty-collection large"><strong>尚无测试场景</strong><p>先完成需求与 API 映射，然后在需求中心选择一条或多条需求生成场景。</p><button className="button primary" onClick={() => onNavigate('requirements')} type="button">前往需求中心</button></div>}</div>
}

function RunDrawer({ run, onClose }: { run: Run; onClose: () => void }) {
  const steps = run.result.steps ?? []
  return <div className="drawer-layer" role="dialog" aria-modal="true" aria-label="运行详情"><button className="drawer-scrim" onClick={onClose} aria-label="关闭" type="button" /><aside className="run-drawer"><header><div><span className={`status ${run.status}`}>{run.status === 'passed' ? '执行通过' : '执行失败'}</span><h2>{run.scenario_name}</h2><p>{run.id} · {run.environment.toUpperCase()} · {run.result.mode ?? 'simulated'}</p></div><button className="icon-button" onClick={onClose} type="button"><X size={19} /></button></header><div className="run-score"><strong>{run.pass_rate}%</strong><span>场景通过率</span></div><section><h3>步骤证据</h3>{steps.map((step, index) => <div className="evidence-row" key={index}><span>{index + 1}</span><div><strong>{String(step.operation_id ?? step.step_id)}</strong><p>{String((step.request as { method?: string })?.method ?? '')} {String((step.request as { path?: string })?.path ?? '')}</p></div><CheckCircle2 size={17} /></div>)}</section><section><h3>清理结果</h3><div className="cleanup-result"><CheckCircle2 size={17} /> finally cleanup 已完成</div></section></aside></div>
}

function Toast({ message }: { message: string }) { return <div className="toast"><CheckCircle2 size={17} /> {message}</div> }
