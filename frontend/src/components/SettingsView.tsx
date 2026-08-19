import { CheckCircle2, KeyRound, LockKeyhole, Save, ServerCog, Wifi } from 'lucide-react'
import { useState } from 'react'
import type { LlmConfiguration, LlmConfigurationUpdate } from '../types'

interface SettingsViewProps {
  configuration: LlmConfiguration
  onSave: (payload: LlmConfigurationUpdate) => Promise<void>
  onTest: () => Promise<void>
}

const PROVIDER_DEFAULTS: Record<LlmConfiguration['provider'], { model: string; baseUrl: string }> = {
  openai: { model: '', baseUrl: 'https://api.openai.com/v1' },
  azure_openai: { model: '', baseUrl: '' },
  anthropic: { model: '', baseUrl: 'https://api.anthropic.com/v1' },
  openai_compatible: { model: '', baseUrl: '' },
}

export function SettingsView({ configuration, onSave, onTest }: SettingsViewProps) {
  const [provider, setProvider] = useState(configuration.provider)
  const [model, setModel] = useState(configuration.model)
  const [baseUrl, setBaseUrl] = useState(configuration.base_url)
  const [apiKey, setApiKey] = useState('')
  const [enabled, setEnabled] = useState(configuration.enabled)
  const [clearApiKey, setClearApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const selectProvider = (next: LlmConfiguration['provider']) => {
    const defaults = PROVIDER_DEFAULTS[next]
    setProvider(next)
    setModel(defaults.model)
    setBaseUrl(defaults.baseUrl)
  }

  const save = async () => {
    setSaving(true)
    try {
      await onSave({
        provider,
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
      <header className="view-header"><div><h1>系统设置</h1><p>配置用于需求理解和场景生成的 LLM Provider；运行密钥不会进入 Git。</p></div></header>
      <div className="settings-layout">
        <section className="settings-panel">
          <div className="settings-panel-title"><div className="settings-icon"><ServerCog size={20} /></div><div><h2>AI / LLM</h2><p>支持官方 Provider 和 OpenAI 兼容服务。</p></div><label className="switch-row"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用</label></div>
          <div className="provider-grid">
            {(['openai', 'azure_openai', 'anthropic', 'openai_compatible'] as const).map((item) => (
              <button className={provider === item ? 'selected' : ''} onClick={() => selectProvider(item)} type="button" key={item}>{providerLabel(item)}{provider === item ? <CheckCircle2 size={15} /> : null}</button>
            ))}
          </div>
          <div className="settings-form">
            <label>模型名称<input value={model} onChange={(event) => setModel(event.target.value)} placeholder="例如 gpt-5 或内部部署模型名" /></label>
            <label>Base URL<input type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" /></label>
            <label>API Key<div className="secret-input"><KeyRound size={16} /><input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={configuration.has_api_key ? `${configuration.api_key_masked}（留空则保持不变）` : '输入后仅写入本机 Secret Store'} /></div></label>
            {configuration.has_api_key ? <label className="clear-secret"><input type="checkbox" checked={clearApiKey} onChange={(event) => setClearApiKey(event.target.checked)} />保存时清除当前 API Key</label> : null}
          </div>
          <footer><button className="button secondary" disabled={!configuration.has_api_key || testing} onClick={() => void test()} type="button"><Wifi size={16} />{testing ? '连接中…' : '测试连接'}</button><button className="button primary" disabled={!model || saving} onClick={() => void save()} type="button"><Save size={16} />{saving ? '保存中…' : '保存配置'}</button></footer>
        </section>
        <aside className="security-panel">
          <LockKeyhole size={28} />
          <h2>本地敏感信息策略</h2>
          <p>API Key 写入 <code>backend/.local/secrets.json</code>。数据库只保存 Provider、模型和 Base URL，前端只能看到掩码。</p>
          <ul><li>目录已加入 <code>.gitignore</code></li><li>接口不会返回完整密钥</li><li>需求附件和知识文件同样保存在本地忽略目录</li><li>连接测试阻止内网与回环目标</li></ul>
          <div className="storage-status"><LockKeyhole size={15} /><span><strong>{configuration.has_api_key ? '密钥已配置' : '尚未配置密钥'}</strong><small>存储方式：Local only</small></span></div>
        </aside>
      </div>
    </div>
  )
}

function providerLabel(provider: LlmConfiguration['provider']): string {
  return {
    openai: 'OpenAI',
    azure_openai: 'Azure OpenAI',
    anthropic: 'Anthropic',
    openai_compatible: 'OpenAI 兼容',
  }[provider]
}
