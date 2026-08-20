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
import { SettingsView } from './components/SettingsView'
import { Sidebar } from './components/Sidebar'
import { SourceCenter } from './components/SourceCenter'
import { WorkflowEditor } from './components/WorkflowEditor'
import { ApiView, ReportsView, RequirementsView } from './components/WorkspaceViews'
import type {
  ApiSpecType, Dashboard, DocumentItem, EnvironmentItem, KnowledgeBaseItem,
  LlmConfiguration, LlmConfigurationUpdate, NavKey, OperationGraph, Project,
  McpServerCandidate, McpServerConfiguration, McpServerConfigurationUpdate,
  RequirementItem, Run, Scenario, SourceConnector, SourceConnectorCreate,
  TapdMcpConnect, TapdMcpProjects,
} from './types'

interface ProjectData {
  documents: DocumentItem[]
  requirements: RequirementItem[]
  operationGraph: OperationGraph
  scenarios: Scenario[]
  environments: EnvironmentItem[]
  sources: SourceConnector[]
  knowledgeBases: KnowledgeBaseItem[]
}

const EMPTY_DATA: ProjectData = {
  documents: [], requirements: [], operationGraph: { nodes: [], edges: [], groups: [] }, scenarios: [], environments: [],
  sources: [], knowledgeBases: [],
}
const EMPTY_LLM_CONFIGURATION: LlmConfiguration = {
  provider: 'openai', model: '', base_url: '', enabled: false,
  has_api_key: false, api_key_masked: '', storage: 'local_only', updated_at: null,
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProjectId, setActiveProjectId] = useState('')
  const [nav, setNav] = useState<NavKey>('overview')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [data, setData] = useState<ProjectData>(EMPTY_DATA)
  const [llmConfiguration, setLlmConfiguration] = useState<LlmConfiguration>(EMPTY_LLM_CONFIGURATION)
  const [mcpServers, setMcpServers] = useState<McpServerConfiguration[]>([])
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

  const loadProject = useCallback(async (projectId: string, showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const [dashboardResult, documents, requirements, operationGraph, scenarios, environments, sources, knowledgeBases] = await Promise.all([
        api.dashboard(projectId), api.documents(projectId), api.requirements(projectId),
        api.operationGraph(projectId), api.scenarios(projectId), api.environments(projectId),
        api.sources(projectId), api.knowledgeBases(projectId),
      ])
      setActiveProjectId(projectId)
      setDashboard(dashboardResult)
      setData({ documents, requirements, operationGraph, scenarios, environments, sources, knowledgeBases })
      setSelectedScenarioId((current) => scenarios.some((item) => item.id === current) ? current : scenarios[0]?.id ?? '')
      setEnvironmentId((current) => environments.some((item) => item.id === current) ? current : environments.find((item) => item.is_default)?.id ?? environments[0]?.id ?? '')
    } catch (error) {
      setToast(error instanceof Error ? error.message : '加载项目失败')
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [])

  const bootstrap = useCallback(async () => {
    setLoading(true)
    try {
      const [projectRows, llm, managedMcpServers] = await Promise.all([
        api.projects(), api.llmConfiguration(), api.mcpServers(),
      ])
      setProjects(projectRows)
      setLlmConfiguration(llm)
      setMcpServers(managedMcpServers)
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
    setToast('项目已创建。请在接入中心选择需求与 API 来源。')
  }

  const refreshProject = async () => { if (activeProjectId) await loadProject(activeProjectId, false) }

  const uploadRequirement = async (file: File) => {
    if (!activeProjectId) return
    try {
      await api.uploadDocument(activeProjectId, 'requirement', file)
      await refreshProject()
      setToast(`${file.name} 已完成版本化保存与解析`)
    } catch (error) { setToast(error instanceof Error ? error.message : '上传失败') }
  }

  const uploadApi = async (specType: ApiSpecType, file: File) => {
    if (!activeProjectId) return
    try {
      const document = await api.uploadDocument(activeProjectId, 'api', file, specType)
      await refreshProject()
      setToast(`${file.name} 已识别为 ${document.kind}，并完成 Operation 归一化`)
    } catch (error) { setToast(error instanceof Error ? error.message : 'API 文档上传失败') }
  }

  const importApiUrl = async (url: string, specType: ApiSpecType) => {
    if (!activeProjectId) return
    try {
      const document = await api.importApiUrl(activeProjectId, url, specType)
      await refreshProject()
      setToast(`已从 HTTPS URL 导入 ${document.kind} 文档`)
    } catch (error) { setToast(error instanceof Error ? error.message : 'URL 导入失败') }
  }

  const createSource = async (payload: SourceConnectorCreate) => {
    if (!activeProjectId) return
    try {
      await api.createSource(activeProjectId, payload)
      await refreshProject()
      setToast('来源已保存；Secret 仅写入本机存储')
    } catch (error) { setToast(error instanceof Error ? error.message : '来源保存失败') }
  }

  const syncSource = async (sourceId: string) => {
    try {
      const document = await api.syncSource(sourceId)
      await refreshProject()
      setToast(`${document.name} 已同步并解析`)
    } catch (error) { setToast(error instanceof Error ? error.message : '来源同步失败') }
  }

  const discoverTapdMcp = async (endpointUrl: string): Promise<McpServerCandidate[]> => {
    try {
      const servers = await api.discoverTapdMcp(endpointUrl)
      setToast(servers.some((item) => item.tapd_capable) ? '已发现可用的 TAPD MCP Server' : '已完成 MCP 配置扫描，请查看检测结果')
      return servers
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'MCP 自动检测失败')
      throw error
    }
  }

  const loadTapdProjects = async (endpointUrl: string): Promise<TapdMcpProjects> => {
    try {
      return await api.tapdMcpProjects(endpointUrl)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'TAPD 项目列表读取失败')
      throw error
    }
  }

  const connectTapdMcp = async (payload: TapdMcpConnect) => {
    if (!activeProjectId) return
    try {
      await api.connectTapdMcp(activeProjectId, payload)
      await refreshProject()
      setToast(`已通过本地 MCP 绑定 TAPD 项目：${payload.tapd_project_name || payload.tapd_project_id}`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'TAPD MCP 连接失败')
      throw error
    }
  }

  const createKnowledgeBase = async (payload: { name: string; description: string }) => {
    if (!activeProjectId) return
    try {
      await api.createKnowledgeBase(activeProjectId, payload)
      await refreshProject()
      setToast('组件知识库已创建，本地私有目录已就绪')
    } catch (error) { setToast(error instanceof Error ? error.message : '知识库创建失败') }
  }

  const uploadKnowledge = async (knowledgeBaseId: string, file: File) => {
    try {
      await api.uploadKnowledgeDocument(knowledgeBaseId, file)
      await refreshProject()
      setToast(`${file.name} 已保存到本机组件知识库`)
    } catch (error) { setToast(error instanceof Error ? error.message : '知识文件上传失败') }
  }

  const extractKnowledge = async (knowledgeBaseId: string) => {
    try {
      const result = await api.extractKnowledgeRequirements(knowledgeBaseId)
      await refreshProject()
      setToast(`已从 ${result.documents} 个私有文件中提取 ${result.requirements} 条需求`)
    } catch (error) { setToast(error instanceof Error ? error.message : '知识库解析失败') }
  }

  const saveLlmConfiguration = async (payload: LlmConfigurationUpdate) => {
    try {
      const updated = await api.updateLlmConfiguration(payload)
      setLlmConfiguration(updated)
      setToast('LLM 配置已保存；API Key 未写入数据库或 Git 工作区')
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'LLM 配置保存失败')
      throw error
    }
  }

  const testLlmConfiguration = async () => {
    try {
      const result = await api.testLlmConfiguration()
      setToast(`${result.provider} / ${result.model} 连接测试通过`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'LLM 连接测试失败')
      throw error
    }
  }

  const saveMcpServer = async (
    serverId: string | null,
    payload: McpServerConfigurationUpdate,
  ) => {
    try {
      if (serverId) await api.updateMcpServer(serverId, payload)
      else await api.createMcpServer(payload)
      setMcpServers(await api.mcpServers())
      setToast(`MCP Server 已${serverId ? '更新' : '添加'}，凭据仅保存在本机`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'MCP 配置保存失败')
      throw error
    }
  }

  const deleteMcpServer = async (serverId: string) => {
    try {
      await api.deleteMcpServer(serverId)
      setMcpServers((current) => current.filter((item) => item.id !== serverId))
      setToast('MCP Server 及其本地凭据已删除')
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'MCP Server 删除失败')
      throw error
    }
  }

  const testMcpServer = async (serverId: string): Promise<McpServerCandidate> => {
    try {
      const result = await api.testMcpServer(serverId)
      setToast(result.connectable ? `MCP 连接成功，发现 ${result.tools.length} 个工具` : `MCP 连接失败：${result.error}`)
      return result
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'MCP 连接测试失败')
      throw error
    }
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
  if (!dashboard && nav === 'settings') return <main className="standalone-settings"><button className="button secondary" onClick={() => setNav('overview')} type="button">返回首页</button><SettingsView key={llmConfiguration.updated_at ?? 'empty'} configuration={llmConfiguration} mcpServers={mcpServers} onSave={saveLlmConfiguration} onTest={testLlmConfiguration} onSaveMcp={saveMcpServer} onDeleteMcp={deleteMcpServer} onTestMcp={testMcpServer} onDiscoverMcp={() => discoverTapdMcp('')} />{toast ? <Toast message={toast} /> : null}</main>
  if (!dashboard) return <><EmptyWorkspace onCreate={() => setProjectModalOpen(true)} onSettings={() => setNav('settings')} />{projectModalOpen ? <ProjectModal onClose={() => setProjectModalOpen(false)} onCreate={createProject} /> : null}{toast ? <Toast message={toast} /> : null}</>

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
          {nav === 'documents' ? <SourceCenter documents={data.documents} sources={data.sources} knowledgeBases={data.knowledgeBases} onUploadRequirement={uploadRequirement} onUploadApi={uploadApi} onImportApiUrl={importApiUrl} onCreateSource={createSource} onSyncSource={syncSource} onDiscoverTapdMcp={discoverTapdMcp} onLoadTapdProjects={loadTapdProjects} onConnectTapdMcp={connectTapdMcp} onCreateKnowledgeBase={createKnowledgeBase} onUploadKnowledge={uploadKnowledge} onExtractKnowledge={extractKnowledge} /> : null}
          {nav === 'requirements' ? <RequirementsView requirements={data.requirements} onApprove={approveRequirement} onAnalyze={analyze} onGenerate={generateScenario} /> : null}
          {nav === 'api' ? <ApiView key={activeProjectId} graph={data.operationGraph} /> : null}
          {nav === 'scenarios' ? <ScenarioWorkspace scenarios={data.scenarios} activeScenario={activeScenario} selectedId={selectedScenarioId} onSelect={setSelectedScenarioId} running={running} runMode={runMode} onModeChange={setRunMode} onRun={runScenario} onApprove={approveScenario} onSave={saveScenario} onNavigate={setNav} /> : null}
          {nav === 'reports' ? <ReportsView runs={dashboard.recent_runs} projectId={dashboard.project.id} onSelect={setSelectedRun} /> : null}
          {nav === 'settings' ? <SettingsView key={llmConfiguration.updated_at ?? 'empty'} configuration={llmConfiguration} mcpServers={mcpServers} onSave={saveLlmConfiguration} onTest={testLlmConfiguration} onSaveMcp={saveMcpServer} onDeleteMcp={deleteMcpServer} onTestMcp={testMcpServer} onDiscoverMcp={() => discoverTapdMcp('')} /> : null}
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
  return <section className="getting-started"><header><div><h2>建立第一个测试闭环</h2><p>当前项目是空白工作区，不包含任何演示业务或虚构接口。</p></div><span>0 / 3</span></header><div className="setup-actions"><button onClick={() => onNavigate('documents')} type="button"><FileText size={22} /><div><strong>1. 选择需求来源</strong><p>文件、TAPD、外部或组件知识库</p></div><Plus size={16} /></button><button onClick={() => onNavigate('documents')} type="button"><FileCode2 size={22} /><div><strong>2. 导入 API 资产</strong><p>OpenAPI、Swagger、Postman、HAR</p></div><Plus size={16} /></button><button onClick={() => onNavigate('requirements')} type="button"><GitFork size={22} /><div><strong>3. 分析并生成场景</strong><p>审核映射、断言和清理计划</p></div><Plus size={16} /></button></div></section>
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
