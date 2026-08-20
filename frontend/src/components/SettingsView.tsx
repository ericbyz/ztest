import {
  CheckCircle2,
  KeyRound,
  Link2,
  LockKeyhole,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Server,
  ServerCog,
  Trash2,
  Wifi,
  X,
} from 'lucide-react'
import { useState } from 'react'
import type {
  LlmConfiguration,
  LlmConfigurationUpdate,
  McpServerCandidate,
  McpServerConfiguration,
  McpServerConfigurationUpdate,
} from '../types'

interface SettingsViewProps {
  configuration: LlmConfiguration
  mcpServers: McpServerConfiguration[]
  onSave: (payload: LlmConfigurationUpdate) => Promise<void>
  onTest: () => Promise<void>
  onSaveMcp: (serverId: string | null, payload: McpServerConfigurationUpdate) => Promise<void>
  onDeleteMcp: (serverId: string) => Promise<void>
  onTestMcp: (serverId: string) => Promise<McpServerCandidate>
  onDiscoverMcp: () => Promise<McpServerCandidate[]>
}

const PROVIDER_DEFAULTS: Record<LlmConfiguration['provider'], { model: string; baseUrl: string }> = {
  openai: { model: '', baseUrl: 'https://api.openai.com/v1' },
  azure_openai: { model: '', baseUrl: '' },
  anthropic: { model: '', baseUrl: 'https://api.anthropic.com/v1' },
  openai_compatible: { model: '', baseUrl: '' },
}

type ProviderChoice = LlmConfiguration['provider'] | 'deepseek'

const PROVIDER_CHOICES: ProviderChoice[] = [
  'deepseek', 'openai', 'azure_openai', 'anthropic', 'openai_compatible',
]

const DEEPSEEK_DEFAULT = {
  model: 'deepseek-v4-flash',
  baseUrl: 'https://api.deepseek.com',
}

function choiceFromConfiguration(configuration: LlmConfiguration): ProviderChoice {
  if (
    configuration.provider === 'openai_compatible'
    && configuration.base_url.toLowerCase().includes('deepseek.com')
  ) return 'deepseek'
  return configuration.provider
}

export function SettingsView(props: SettingsViewProps) {
  const { configuration, onSave, onTest } = props
  const [providerChoice, setProviderChoice] = useState<ProviderChoice>(() => choiceFromConfiguration(configuration))
  const [model, setModel] = useState(configuration.model)
  const [baseUrl, setBaseUrl] = useState(configuration.base_url)
  const [apiKey, setApiKey] = useState('')
  const [enabled, setEnabled] = useState(configuration.enabled)
  const [clearApiKey, setClearApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const selectProvider = (next: ProviderChoice) => {
    const defaults = next === 'deepseek' ? DEEPSEEK_DEFAULT : PROVIDER_DEFAULTS[next]
    setProviderChoice(next)
    setModel(defaults.model)
    setBaseUrl(defaults.baseUrl)
  }

  const save = async () => {
    setSaving(true)
    try {
      await onSave({
        provider: providerChoice === 'deepseek' ? 'openai_compatible' : providerChoice,
        model,
        base_url: baseUrl,
        enabled,
        api_key: apiKey || undefined,
        clear_api_key: clearApiKey,
      })
      setApiKey('')
      setClearApiKey(false)
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setTesting(true)
    try { await onTest() } finally { setTesting(false) }
  }

  return (
    <div className="workspace-view settings-view">
      <header className="view-header"><div><h1>系统设置</h1><p>统一管理 LLM 与 MCP 连接；运行密钥不会进入 Git。</p></div></header>
      <div className="settings-layout">
        <div className="settings-main-stack">
          <section className="settings-panel">
            <div className="settings-panel-title"><div className="settings-icon"><ServerCog size={20} /></div><div><h2>AI / LLM</h2><p>支持官方 Provider 和 OpenAI 兼容服务。</p></div><label className="switch-row"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用</label></div>
            <div className={`saved-llm-summary ${configuration.updated_at ? '' : 'empty'}`}>
              <span className="saved-llm-icon"><CheckCircle2 size={17} /></span>
              <div>
                <strong>{configuration.updated_at ? '当前已保存配置' : '尚未保存完整配置'}</strong>
                <p>
                  {configuration.updated_at
                    ? `${providerDisplayName(configuration)} · ${configuration.model || '未填写模型'}`
                    : '请选择 Provider 并填写模型，然后保存配置。'}
                </p>
                {configuration.updated_at && configuration.base_url ? <code>{configuration.base_url}</code> : null}
              </div>
              <span className={`configuration-state ${configuration.enabled ? 'enabled' : ''}`}>
                {configuration.enabled ? '已启用' : '未启用'}
              </span>
            </div>
            <div className="provider-grid">
              {PROVIDER_CHOICES.map((item) => (
                <button className={providerChoice === item ? 'selected' : ''} onClick={() => selectProvider(item)} type="button" key={item}>{providerLabel(item)}{providerChoice === item ? <CheckCircle2 size={15} /> : null}</button>
              ))}
            </div>
            <div className="settings-form">
              <label>模型名称<input value={model} onChange={(event) => setModel(event.target.value)} placeholder="例如 gpt-5 或内部部署模型名" /></label>
              <label>Base URL<input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" /></label>
              <label>API Key<div className="secret-input"><KeyRound size={16} /><input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={configuration.has_api_key ? `${configuration.api_key_masked}（留空则保持不变）` : '输入后仅写入本机 Secret Store'} /></div></label>
              {configuration.has_api_key ? <div className="saved-secret-status"><LockKeyhole size={14} />API Key 已保存在本机：<code>{configuration.api_key_masked}</code></div> : null}
              {configuration.has_api_key ? <label className="clear-secret"><input type="checkbox" checked={clearApiKey} onChange={(event) => setClearApiKey(event.target.checked)} />保存时清除当前 API Key</label> : null}
            </div>
            <footer><button className="button secondary" disabled={!configuration.has_api_key || testing} onClick={() => void test()} type="button"><Wifi size={16} />{testing ? '连接中…' : '测试连接'}</button><button className="button primary" disabled={!model || saving} onClick={() => void save()} type="button"><Save size={16} />{saving ? '保存中…' : '保存配置'}</button></footer>
          </section>
          <McpSettingsPanel {...props} />
        </div>
        <aside className="security-panel">
          <LockKeyhole size={28} />
          <h2>本地敏感信息策略</h2>
          <p>API Key 和 MCP 认证值写入 <code>backend/.local/secrets.json</code>。MCP 非敏感元数据写入同目录的 <code>mcp_servers.json</code>。</p>
          <ul><li>整个目录已加入 <code>.gitignore</code></li><li>接口不会返回完整密钥</li><li>不执行 Claude/Cursor 配置中的任意命令</li><li>连接测试不跟随重定向</li></ul>
          <div className="storage-status"><LockKeyhole size={15} /><span><strong>本机隔离存储</strong><small>Local only · Git ignored</small></span></div>
        </aside>
      </div>
    </div>
  )
}

const EMPTY_MCP: McpServerConfigurationUpdate = {
  name: '',
  endpoint_url: '',
  transport: 'streamable_http',
  auth_type: 'none',
  auth_header: 'Authorization',
  secret: '',
  enabled: true,
}

function McpSettingsPanel(props: SettingsViewProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [draft, setDraft] = useState<McpServerConfigurationUpdate>(EMPTY_MCP)
  const [busy, setBusy] = useState('')
  const [discovered, setDiscovered] = useState<McpServerCandidate[]>([])
  const [results, setResults] = useState<Record<string, McpServerCandidate>>({})

  const create = (candidate?: McpServerCandidate) => {
    setEditingId(null)
    setDraft({ ...EMPTY_MCP, name: candidate?.name ?? '', endpoint_url: candidate?.endpoint_url ?? '' })
    setEditorOpen(true)
  }

  const edit = (server: McpServerConfiguration) => {
    setEditingId(server.id)
    setDraft({
      name: server.name,
      endpoint_url: server.endpoint_url,
      transport: server.transport,
      auth_type: server.auth_type,
      auth_header: server.auth_header,
      secret: '',
      enabled: server.enabled,
    })
    setEditorOpen(true)
  }

  const save = async () => {
    setBusy('save')
    try {
      await props.onSaveMcp(editingId, { ...draft, secret: draft.secret || undefined })
      setEditorOpen(false)
      setEditingId(null)
      setDraft(EMPTY_MCP)
    } finally { setBusy('') }
  }

  const scan = async () => {
    setBusy('scan')
    try { setDiscovered(await props.onDiscoverMcp()) } finally { setBusy('') }
  }

  const test = async (serverId: string) => {
    setBusy(`test:${serverId}`)
    try {
      const result = await props.onTestMcp(serverId)
      setResults((current) => ({ ...current, [serverId]: result }))
    } finally { setBusy('') }
  }

  const remove = async (server: McpServerConfiguration) => {
    if (!window.confirm(`确定删除 MCP Server“${server.name}”及其本地凭据？`)) return
    setBusy(`delete:${server.id}`)
    try { await props.onDeleteMcp(server.id) } finally { setBusy('') }
  }

  return (
    <section className="settings-panel mcp-settings-panel">
      <div className="settings-panel-title"><div className="settings-icon"><Server size={20} /></div><div><h2>MCP Server</h2><p>管理 Streamable HTTP 服务，并从 Claude Code、Codex、Cursor 扫描已注册地址。</p></div><button className="button secondary" onClick={() => create()} type="button"><Plus size={15} />添加</button></div>

      <div className="mcp-toolbar"><button className="button secondary" disabled={busy === 'scan'} onClick={() => void scan()} type="button"><RefreshCw className={busy === 'scan' ? 'spinning' : ''} size={15} />{busy === 'scan' ? '正在扫描' : '扫描本机配置'}</button><span>仅读取服务名和地址，不会启动 stdio 命令。</span></div>

      {discovered.length > 0 ? <div className="mcp-discovered"><strong>扫描结果</strong>{discovered.map((server, index) => <div className="mcp-config-row compact" key={`${server.name}-${server.endpoint_url}-${index}`}><span className={`connection-dot ${server.connectable ? 'ready' : 'failed'}`} /><div><b>{server.name}</b><small>{displayMcpEndpoint(server.endpoint_url)}</small></div><span className={server.connectable ? 'mcp-ready' : 'mcp-unavailable'}>{server.connectable ? (server.tapd_capable ? 'TAPD 可用' : '已连接') : server.error}</span>{server.endpoint_url ? <button className="link-button" onClick={() => create(server)} type="button">导入</button> : null}</div>)}</div> : null}

      <div className="mcp-config-list">
        {props.mcpServers.length === 0 ? <div className="mcp-empty"><Link2 size={22} /><div><strong>尚未添加 MCP Server</strong><p>可手工配置，或先扫描 Claude Code 中的已注册服务。</p></div></div> : props.mcpServers.map((server) => {
          const result = results[server.id]
          return <article className="mcp-config-row" key={server.id}><span className={`connection-dot ${result?.connectable ? 'ready' : result ? 'failed' : server.enabled ? 'idle' : 'disabled'}`} /><div><strong>{server.name}</strong><p>{displayMcpEndpoint(server.endpoint_url)}</p><small>{server.enabled ? 'Enabled' : 'Disabled'} · {server.auth_type === 'none' ? '无认证' : server.has_secret ? '凭据已配置' : '缺少凭据'}{result ? ` · ${result.connectable ? `连接成功，${result.tools.length} 个工具` : result.error}` : ''}</small></div><div className="mcp-row-actions"><button className="button secondary" disabled={!server.enabled || busy === `test:${server.id}`} onClick={() => void test(server.id)} type="button"><Wifi size={14} />{busy === `test:${server.id}` ? '测试中' : '测试'}</button><button className="icon-button" aria-label={`编辑 ${server.name}`} onClick={() => edit(server)} type="button"><Pencil size={15} /></button><button className="icon-button danger" aria-label={`删除 ${server.name}`} disabled={busy === `delete:${server.id}`} onClick={() => void remove(server)} type="button"><Trash2 size={15} /></button></div></article>
        })}
      </div>

      {editorOpen ? <div className="mcp-config-editor"><header><div><strong>{editingId ? '编辑 MCP Server' : '添加 MCP Server'}</strong><p>认证值为只写 Secret，编辑时留空即保持原值。</p></div><button className="icon-button" aria-label="关闭 MCP 配置" onClick={() => setEditorOpen(false)} type="button"><X size={17} /></button></header><div className="form-grid"><label>服务名称<input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="例如 TAPD 本地服务" /></label><label>状态<select value={draft.enabled ? 'enabled' : 'disabled'} onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.value === 'enabled' }))}><option value="enabled">启用</option><option value="disabled">停用</option></select></label><label className="span-2">Streamable HTTP 地址<input type="url" value={draft.endpoint_url} onChange={(event) => setDraft((current) => ({ ...current, endpoint_url: event.target.value }))} placeholder="http://127.0.0.1:3333/mcp" /></label><label>认证方式<select value={draft.auth_type} onChange={(event) => setDraft((current) => ({ ...current, auth_type: event.target.value as McpServerConfiguration['auth_type'] }))}><option value="none">无认证</option><option value="bearer">Bearer Token</option><option value="api_key">API Key Header</option></select></label><label>Header 名称<input disabled={draft.auth_type === 'none'} value={draft.auth_header} onChange={(event) => setDraft((current) => ({ ...current, auth_header: event.target.value }))} /></label>{draft.auth_type !== 'none' ? <label className="span-2">认证 Secret<input type="password" autoComplete="new-password" value={draft.secret ?? ''} onChange={(event) => setDraft((current) => ({ ...current, secret: event.target.value }))} placeholder={editingId ? '留空则保持原凭据' : '仅保存到 backend/.local/secrets.json'} /></label> : null}</div><footer><button className="button secondary" onClick={() => setEditorOpen(false)} type="button">取消</button><button className="button primary" disabled={busy === 'save' || draft.name.trim().length < 2 || !draft.endpoint_url} onClick={() => void save()} type="button"><Save size={15} />{busy === 'save' ? '保存中' : '保存 MCP'}</button></footer></div> : null}
    </section>
  )
}

function providerLabel(provider: ProviderChoice): string {
  return {
    deepseek: 'DeepSeek',
    openai: 'OpenAI',
    azure_openai: 'Azure OpenAI',
    anthropic: 'Anthropic',
    openai_compatible: 'OpenAI 兼容',
  }[provider]
}

function providerDisplayName(configuration: LlmConfiguration): string {
  return providerLabel(choiceFromConfiguration(configuration))
}

function displayMcpEndpoint(endpointUrl: string): string {
  if (!endpointUrl) return 'stdio 配置，无可直连 HTTP 地址'
  try {
    const endpoint = new URL(endpointUrl)
    return ['localhost', '127.0.0.1', '[::1]'].includes(endpoint.hostname)
      ? endpointUrl
      : endpoint.origin
  } catch {
    return '地址格式无效'
  }
}
