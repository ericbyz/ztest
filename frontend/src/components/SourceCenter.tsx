import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  CloudDownload,
  Database,
  FileCode2,
  FileText,
  FolderLock,
  Link2,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Upload,
} from 'lucide-react'
import { useRef, useState } from 'react'
import type {
  ApiSpecType,
  DocumentItem,
  KnowledgeBaseItem,
  McpServerCandidate,
  SourceConnector,
  SourceConnectorCreate,
  TapdMcpConnect,
  TapdMcpProjects,
} from '../types'

type SourceTab = 'requirements' | 'api' | 'knowledge'

interface SourceCenterProps {
  documents: DocumentItem[]
  sources: SourceConnector[]
  knowledgeBases: KnowledgeBaseItem[]
  onUploadRequirement: (file: File) => Promise<void>
  onUploadApi: (type: ApiSpecType, file: File) => Promise<void>
  onImportApiUrl: (url: string, type: ApiSpecType) => Promise<void>
  onCreateSource: (payload: SourceConnectorCreate) => Promise<void>
  onSyncSource: (sourceId: string) => Promise<void>
  onDiscoverTapdMcp: (endpointUrl: string) => Promise<McpServerCandidate[]>
  onLoadTapdProjects: (endpointUrl: string) => Promise<TapdMcpProjects>
  onConnectTapdMcp: (payload: TapdMcpConnect) => Promise<void>
  onCreateKnowledgeBase: (payload: { name: string; description: string }) => Promise<void>
  onUploadKnowledge: (knowledgeBaseId: string, file: File) => Promise<void>
  onExtractKnowledge: (knowledgeBaseId: string) => Promise<void>
}

const EMPTY_CONNECTOR: SourceConnectorCreate = {
  name: '',
  source_type: 'tapd',
  endpoint_url: '',
  workspace_id: '',
  auth_type: 'bearer',
  auth_header: 'Authorization',
  secret: '',
  request_params: {},
}

const SPEC_LABELS: Record<ApiSpecType, string> = {
  auto: '自动识别',
  openapi: 'OpenAPI 3.x',
  swagger: 'Swagger 2.0',
  postman: 'Postman Collection 2.x',
  har: 'HAR 1.2',
}

export function SourceCenter(props: SourceCenterProps) {
  const [tab, setTab] = useState<SourceTab>('requirements')
  const [apiType, setApiType] = useState<ApiSpecType>('auto')
  const [apiUrl, setApiUrl] = useState('')
  const [connector, setConnector] = useState<SourceConnectorCreate>(EMPTY_CONNECTOR)
  const [showConnector, setShowConnector] = useState(false)
  const [showTapdMcp, setShowTapdMcp] = useState(false)
  const [manualMcpUrl, setManualMcpUrl] = useState('')
  const [mcpServers, setMcpServers] = useState<McpServerCandidate[]>([])
  const [selectedMcpUrl, setSelectedMcpUrl] = useState('')
  const [tapdProjects, setTapdProjects] = useState<TapdMcpProjects>({ projects: [], project_tool: '', requirement_tool: '' })
  const [tapdProjectId, setTapdProjectId] = useState('')
  const [tapdProjectName, setTapdProjectName] = useState('')
  const [tapdConnectionName, setTapdConnectionName] = useState('TAPD MCP')
  const [mcpBusy, setMcpBusy] = useState(false)
  const [mcpError, setMcpError] = useState('')
  const [knowledgeName, setKnowledgeName] = useState('')
  const [knowledgeDescription, setKnowledgeDescription] = useState('')
  const [knowledgeTarget, setKnowledgeTarget] = useState('')
  const requirementFileRef = useRef<HTMLInputElement>(null)
  const apiFileRef = useRef<HTMLInputElement>(null)
  const knowledgeFileRef = useRef<HTMLInputElement>(null)

  const openConnector = (sourceType: SourceConnectorCreate['source_type']) => {
    setConnector({
      ...EMPTY_CONNECTOR,
      source_type: sourceType,
      name: sourceType === 'tapd' ? 'TAPD 需求' : '外部知识库',
    })
    setShowConnector(true)
  }

  const loadMcpProjects = async (endpointUrl: string) => {
    setSelectedMcpUrl(endpointUrl)
    setMcpError('')
    setTapdProjectId('')
    setTapdProjectName('')
    try {
      const result = await props.onLoadTapdProjects(endpointUrl)
      setTapdProjects(result)
      const first = result.projects[0]
      if (first) {
        setTapdProjectId(first.id)
        setTapdProjectName(first.name)
      }
    } catch (error) {
      setTapdProjects({ projects: [], project_tool: '', requirement_tool: '' })
      setMcpError(error instanceof Error ? error.message : '无法读取 TAPD 项目')
    }
  }

  const discoverMcp = async () => {
    setMcpBusy(true)
    setMcpError('')
    setMcpServers([])
    try {
      const servers = await props.onDiscoverTapdMcp(manualMcpUrl.trim())
      setMcpServers(servers)
      const match = servers.find((item) => item.connectable && item.tapd_capable)
      if (match) await loadMcpProjects(match.endpoint_url)
      else setMcpError('没有发现可用的 TAPD MCP。若已显示配置错误，请先修复对应 MCP 服务；也可填写回环地址后重试。')
    } catch (error) {
      setMcpError(error instanceof Error ? error.message : 'MCP 自动检测失败')
    } finally {
      setMcpBusy(false)
    }
  }

  const openTapdMcp = () => {
    setShowTapdMcp(true)
    setShowConnector(false)
    if (mcpServers.length === 0) void discoverMcp()
  }

  const connectMcp = async () => {
    const selectedProject = tapdProjects.projects.find((item) => item.id === tapdProjectId)
    setMcpBusy(true)
    setMcpError('')
    try {
      await props.onConnectTapdMcp({
        endpoint_url: selectedMcpUrl,
        tapd_project_id: tapdProjectId,
        tapd_project_name: selectedProject?.name || tapdProjectName,
        name: tapdConnectionName,
      })
      setShowTapdMcp(false)
    } catch (error) {
      setMcpError(error instanceof Error ? error.message : 'TAPD MCP 连接失败')
    } finally {
      setMcpBusy(false)
    }
  }

  const submitConnector = async () => {
    await props.onCreateSource(connector)
    setConnector(EMPTY_CONNECTOR)
    setShowConnector(false)
  }

  const submitKnowledgeBase = async () => {
    await props.onCreateKnowledgeBase({
      name: knowledgeName,
      description: knowledgeDescription,
    })
    setKnowledgeName('')
    setKnowledgeDescription('')
  }

  return (
    <div className="workspace-view source-center">
      <header className="view-header">
        <div>
          <h1>接入中心</h1>
          <p>从文件、研发平台、外部知识库和 API 资产建立可追溯测试上下文。</p>
        </div>
        <div className="local-security"><ShieldCheck size={16} /> Secret 与私有文件仅保存在本机</div>
      </header>

      <div className="source-tabs" role="tablist" aria-label="接入类型">
        <button role="tab" aria-selected={tab === 'requirements'} className={tab === 'requirements' ? 'active' : ''} onClick={() => setTab('requirements')} type="button"><FileText size={16} />需求来源</button>
        <button role="tab" aria-selected={tab === 'api'} className={tab === 'api' ? 'active' : ''} onClick={() => setTab('api')} type="button"><FileCode2 size={16} />API 来源</button>
        <button role="tab" aria-selected={tab === 'knowledge'} className={tab === 'knowledge' ? 'active' : ''} onClick={() => setTab('knowledge')} type="button"><FolderLock size={16} />组件知识库</button>
      </div>

      {tab === 'requirements' ? (
        <section className="source-section">
          <div className="source-options">
            <SourceOption icon={FileText} title="需求文档" description="Markdown、TXT、DOCX、JSON、YAML" action="选择文件" onClick={() => requirementFileRef.current?.click()} />
            <SourceOption icon={Database} title="TAPD" description="读取本机 MCP 配置，并选择 TAPD 项目" action="检测 MCP" onClick={openTapdMcp} />
            <SourceOption icon={BookOpen} title="外部知识库" description="连接返回 JSON 或文本的 HTTPS REST API" action="配置连接" onClick={() => openConnector('external_knowledge')} />
          </div>
          <input ref={requirementFileRef} hidden type="file" accept=".md,.txt,.docx,.json,.yaml,.yml" onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void props.onUploadRequirement(file)
            event.currentTarget.value = ''
          }} />

          {showTapdMcp ? (
            <div className="connector-editor mcp-editor">
              <div className="section-title">
                <div><strong>连接已注册的 TAPD MCP</strong><p>自动读取 Codex、Cursor、Claude 等本机配置并完成握手；凭据只在连接时从原配置解析。</p></div>
                <button className="link-button" onClick={() => setShowTapdMcp(false)} type="button">取消</button>
              </div>
              <div className="mcp-discovery-row">
                <label>回环 MCP 地址（可选）<input type="url" placeholder="http://127.0.0.1:3000/mcp" value={manualMcpUrl} onChange={(event) => setManualMcpUrl(event.target.value)} /></label>
                <button className="button secondary" disabled={mcpBusy} onClick={() => void discoverMcp()} type="button"><RefreshCw className={mcpBusy ? 'spinning' : ''} size={15} />{mcpBusy ? '正在检测' : '自动检测'}</button>
              </div>
              {mcpServers.length > 0 ? (
                <div className="mcp-server-list" role="list" aria-label="发现的 MCP Server">
                  {mcpServers.map((server, index) => (
                    <button
                      className={`mcp-server ${selectedMcpUrl === server.endpoint_url && server.endpoint_url ? 'selected' : ''}`}
                      disabled={!server.connectable || !server.tapd_capable}
                      key={`${server.name}-${server.endpoint_url || index}`}
                      onClick={() => void loadMcpProjects(server.endpoint_url)}
                      type="button"
                    >
                      <span className="mcp-server-icon"><Server size={17} /></span>
                      <span><strong>{server.name}</strong><small>{displayMcpEndpoint(server.endpoint_url)}</small></span>
                      <span className={server.tapd_capable ? 'mcp-ready' : 'mcp-unavailable'}>{server.tapd_capable ? 'TAPD 可用' : server.error}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              {selectedMcpUrl ? (
                <div className="mcp-project-panel">
                  <div className="mcp-connection-ok"><CheckCircle2 size={16} /><span>已连接 MCP：发现需求工具 <code>{tapdProjects.requirement_tool || '正在读取'}</code></span></div>
                  <div className="form-grid">
                    <label>连接名称<input value={tapdConnectionName} onChange={(event) => setTapdConnectionName(event.target.value)} /></label>
                    {tapdProjects.projects.length > 0 ? (
                      <label>选择 TAPD 项目<select value={tapdProjectId} onChange={(event) => {
                        const value = event.target.value
                        setTapdProjectId(value)
                        setTapdProjectName(tapdProjects.projects.find((item) => item.id === value)?.name || '')
                      }}>{tapdProjects.projects.map((project) => <option value={project.id} key={project.id}>{project.name}（{project.id}）</option>)}</select></label>
                    ) : (
                      <label>TAPD 项目 ID<input placeholder="MCP 未提供项目列表时手工填写" value={tapdProjectId} onChange={(event) => setTapdProjectId(event.target.value)} /></label>
                    )}
                  </div>
                  {tapdProjects.projects.length === 0 ? <p className="mcp-hint">该 MCP 没有可调用的项目列表工具，仍可使用项目 ID 建立绑定。</p> : <p className="mcp-hint">已读取 {tapdProjects.projects.length} 个可选项目，同步时只会传入所选项目 ID。</p>}
                </div>
              ) : null}
              {mcpError ? <div className="mcp-error"><AlertTriangle size={15} />{mcpError}</div> : null}
              <button className="button primary" disabled={mcpBusy || !selectedMcpUrl || !tapdProjectId || tapdConnectionName.trim().length < 2} onClick={() => void connectMcp()} type="button"><Link2 size={16} />连接所选项目</button>
            </div>
          ) : null}

          {showConnector ? (
            <div className="connector-editor">
              <div className="section-title"><div><strong>配置外部知识库</strong><p>凭据为写入后不可读取的本地 Secret。</p></div><button className="link-button" onClick={() => setShowConnector(false)} type="button">取消</button></div>
              <div className="form-grid">
                <label>连接名称<input value={connector.name} onChange={(event) => setConnector((current) => ({ ...current, name: event.target.value }))} /></label>
                <label>认证方式<select value={connector.auth_type} onChange={(event) => setConnector((current) => ({ ...current, auth_type: event.target.value as SourceConnectorCreate['auth_type'] }))}><option value="bearer">Bearer Token</option><option value="api_key">API Key Header</option><option value="basic">Basic（用户名:密码）</option><option value="none">无需认证</option></select></label>
                <label className="span-2">HTTPS 查询地址<input type="url" placeholder="https://api.example.com/requirements" value={connector.endpoint_url} onChange={(event) => setConnector((current) => ({ ...current, endpoint_url: event.target.value }))} /></label>
                <label>查询范围 ID<input placeholder="可选" value={connector.workspace_id} onChange={(event) => setConnector((current) => ({ ...current, workspace_id: event.target.value }))} /></label>
                <label>认证 Header<input value={connector.auth_header} onChange={(event) => setConnector((current) => ({ ...current, auth_header: event.target.value }))} /></label>
                <label className="span-2">Secret<input type="password" autoComplete="new-password" placeholder="只写入 backend/.local，不进入数据库或 Git" value={connector.secret ?? ''} onChange={(event) => setConnector((current) => ({ ...current, secret: event.target.value }))} /></label>
              </div>
              <button className="button primary" disabled={!connector.name || !connector.endpoint_url} onClick={() => void submitConnector()} type="button"><Plus size={16} />保存来源</button>
            </div>
          ) : null}

          <div className="source-list">
            <div className="section-title"><div><strong>已连接来源</strong><p>同步结果会形成带来源 URI 的版本化需求文档。</p></div></div>
            {props.sources.length === 0 ? <EmptySource text="尚未配置 TAPD 或外部知识库。" /> : props.sources.map((source) => (
              <article className="source-row" key={source.id}>
                <div className={`source-status ${source.status}`}><Link2 size={17} /></div>
                <div><strong>{source.name}</strong><p>{source.source_type === 'tapd' ? `TAPD · ${source.request_params.tapd_project_name || source.workspace_id}` : '外部知识库'} · {new URL(source.endpoint_url).hostname}</p></div>
                {source.request_params.transport === 'mcp_streamable_http' ? <span className="secret-ok">凭据由 MCP 管理</span> : <span className={source.has_secret ? 'secret-ok' : 'secret-missing'}>{source.has_secret ? 'Secret 已配置' : '缺少 Secret'}</span>}
                <button className="button secondary" onClick={() => void props.onSyncSource(source.id)} type="button"><RefreshCw size={14} />同步</button>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {tab === 'api' ? (
        <section className="source-section api-import-layout">
          <div className="api-import-panel">
            <div className="section-title"><div><strong>上传 API 文档</strong><p>可自动识别，也可明确指定格式。</p></div></div>
            <label>文档类型<select value={apiType} onChange={(event) => setApiType(event.target.value as ApiSpecType)}>{Object.entries(SPEC_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <button className="button primary" onClick={() => apiFileRef.current?.click()} type="button"><Upload size={16} />选择 API 文件</button>
            <input ref={apiFileRef} hidden type="file" accept=".json,.yaml,.yml,.har" onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void props.onUploadApi(apiType, file)
              event.currentTarget.value = ''
            }} />
          </div>
          <div className="api-import-panel">
            <div className="section-title"><div><strong>从 URL 导入</strong><p>仅允许公开 HTTPS 地址并阻止内网目标。</p></div></div>
            <label>文档地址<input type="url" placeholder="https://example.com/openapi.yaml" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} /></label>
            <button className="button secondary" disabled={!apiUrl} onClick={() => void props.onImportApiUrl(apiUrl, apiType).then(() => setApiUrl(''))} type="button"><CloudDownload size={16} />获取并解析</button>
          </div>
          <div className="format-strip">{Object.entries(SPEC_LABELS).filter(([value]) => value !== 'auto').map(([value, label]) => <span key={value}><CheckCircle2 size={13} />{label}</span>)}</div>
        </section>
      ) : null}

      {tab === 'knowledge' ? (
        <section className="source-section knowledge-layout">
          <div className="knowledge-create">
            <div className="section-title"><div><strong>新建组件知识库</strong><p>文件、解析文本和索引均保留在当前机器。</p></div></div>
            <label>知识库名称<input value={knowledgeName} onChange={(event) => setKnowledgeName(event.target.value)} placeholder="例如：支付组件知识库" /></label>
            <label>说明<textarea value={knowledgeDescription} onChange={(event) => setKnowledgeDescription(event.target.value)} placeholder="覆盖的模块、文档范围或维护人" /></label>
            <button className="button primary" disabled={knowledgeName.trim().length < 2} onClick={() => void submitKnowledgeBase()} type="button"><Plus size={16} />创建知识库</button>
          </div>
          <div className="knowledge-list">
            {props.knowledgeBases.length === 0 ? <EmptySource text="尚无组件知识库。创建后可上传私有文件并解析为需求。" /> : props.knowledgeBases.map((knowledgeBase) => (
              <article className="knowledge-card" key={knowledgeBase.id}>
                <div className="knowledge-icon"><FolderLock size={20} /></div>
                <div><strong>{knowledgeBase.name}</strong><p>{knowledgeBase.description || '未填写说明'}</p><small>{knowledgeBase.document_count} 个文件 · {formatBytes(knowledgeBase.size_bytes)}</small></div>
                <div className="knowledge-actions">
                  <button className="button secondary" onClick={() => { setKnowledgeTarget(knowledgeBase.id); knowledgeFileRef.current?.click() }} type="button"><Upload size={14} />上传文件</button>
                  <button className="link-button" disabled={knowledgeBase.document_count === 0} onClick={() => void props.onExtractKnowledge(knowledgeBase.id)} type="button">解析为需求</button>
                </div>
              </article>
            ))}
            <input ref={knowledgeFileRef} hidden type="file" accept=".md,.txt,.docx,.json,.yaml,.yml" onChange={(event) => {
              const file = event.target.files?.[0]
              if (file && knowledgeTarget) void props.onUploadKnowledge(knowledgeTarget, file)
              event.currentTarget.value = ''
            }} />
          </div>
        </section>
      ) : null}

      <section className="asset-history">
        <div className="section-title"><div><strong>接入记录</strong><p>仅显示元数据和校验和，不在页面暴露原始敏感内容。</p></div></div>
        {props.documents.length === 0 ? <EmptySource text="当前项目还没有接入记录。" /> : props.documents.map((document) => (
          <article className="asset-row" key={document.id}>
            <div className={`file-icon ${document.kind}`}>{document.kind === 'requirement' || document.kind === 'knowledge' ? <FileText size={20} /> : <FileCode2 size={20} />}</div>
            <div><strong>{document.name}</strong><p>{sourceLabel(document.source_type)} · v{document.version} · {formatBytes(document.size_bytes)} · SHA-256 {document.checksum.slice(0, 10)}…</p>{document.issues.map((issue) => <span className="inline-warning" key={issue}><AlertTriangle size={12} />{issue}</span>)}</div>
            <span className="asset-kind">{document.kind}</span>
          </article>
        ))}
      </section>
    </div>
  )
}

function SourceOption({ icon: Icon, title, description, action, onClick }: {
  icon: typeof FileText
  title: string
  description: string
  action: string
  onClick: () => void
}) {
  return <article className="source-option"><div><Icon size={22} /></div><strong>{title}</strong><p>{description}</p><button className="link-button" onClick={onClick} type="button">{action}</button></article>
}

function EmptySource({ text }: { text: string }) {
  return <div className="empty-source">{text}</div>
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function sourceLabel(sourceType: string): string {
  return {
    local_file: '本地文件',
    tapd: 'TAPD',
    external_knowledge: '外部知识库',
    component_knowledge: '组件知识库',
    api_url: 'HTTPS URL',
  }[sourceType] ?? sourceType
}

function displayMcpEndpoint(endpointUrl: string): string {
  if (!endpointUrl) return 'stdio MCP 配置'
  try {
    const endpoint = new URL(endpointUrl)
    return ['localhost', '127.0.0.1', '[::1]'].includes(endpoint.hostname)
      ? endpointUrl
      : endpoint.origin
  } catch {
    return 'MCP 地址格式无效'
  }
}
