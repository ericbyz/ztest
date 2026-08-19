import { ArrowRight, FileCode2, FolderPlus, GitFork, Plus, Settings, X } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import type { EnvironmentItem, Project } from '../types'

export function EmptyWorkspace({ onCreate, onSettings }: { onCreate: () => void; onSettings: () => void }) {
  return (
    <main className="empty-workspace">
      <div className="empty-brand"><span>AI</span><strong>AI Test Tool</strong><button className="button secondary" onClick={onSettings} type="button"><Settings size={16} />系统设置</button></div>
      <section className="empty-hero">
        <div className="empty-visual"><GitFork size={42} /></div>
        <h1>从需求建立可执行的 API 测试链路</h1>
        <p>创建第一个项目，然后从文件、TAPD、知识库与多种 API 文档建立测试上下文。工作区不会预置任何业务数据。</p>
        <button className="button primary large" onClick={onCreate} type="button"><FolderPlus size={18} /> 创建项目</button>
      </section>
      <div className="empty-steps">
        <article><b>1</b><FileCode2 size={20} /><div><strong>接入真实资料</strong><p>文件、TAPD、知识库与 API 资产</p></div></article>
        <ArrowRight size={18} />
        <article><b>2</b><GitFork size={20} /><div><strong>审核映射与场景</strong><p>只引用项目内存在的 Operation</p></div></article>
        <ArrowRight size={18} />
        <article><b>3</b><Plus size={20} /><div><strong>执行并沉淀资产</strong><p>保留证据、清理结果并导出 pytest</p></div></article>
      </div>
    </main>
  )
}

export function ProjectModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (payload: { name: string; description: string; default_environment: string }) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [environment, setEnvironment] = useState('test')
  const [saving, setSaving] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    try { await onCreate({ name, description, default_environment: environment }) } finally { setSaving(false) }
  }

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label="创建项目">
      <button className="modal-scrim" onClick={onClose} aria-label="关闭" type="button" />
      <form className="modal-card" onSubmit={(event) => void submit(event)}>
        <header><div><h2>创建测试项目</h2><p>每个项目拥有独立的文档、Operation、场景、环境和运行证据。</p></div><button className="icon-button" onClick={onClose} type="button"><X size={18} /></button></header>
        <label>项目名称<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} placeholder="例如：会员服务 API" /></label>
        <label>项目描述<textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="说明被测系统与测试目标" /></label>
        <label>默认环境<select value={environment} onChange={(event) => setEnvironment(event.target.value)}><option value="local">Local</option><option value="dev">Dev</option><option value="test">Test</option><option value="staging">Staging</option></select></label>
        <footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={saving || name.length < 2} type="submit">{saving ? '创建中…' : '创建并进入'}</button></footer>
      </form>
    </div>
  )
}

export function EnvironmentModal({ project, environments, onClose, onCreate }: {
  project: Project
  environments: EnvironmentItem[]
  onClose: () => void
  onCreate: (payload: Omit<EnvironmentItem, 'id' | 'project_id' | 'created_at'>) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState('test')
  const [baseUrl, setBaseUrl] = useState('')
  const [authType, setAuthType] = useState<EnvironmentItem['auth_type']>('none')
  const [secretRef, setSecretRef] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const host = baseUrl ? new URL(baseUrl).hostname : ''
    await onCreate({ name, kind, base_url: baseUrl, auth_type: authType, auth_header: authType === 'api_key' ? 'X-API-Key' : 'Authorization', secret_ref: secretRef, allow_hosts: host ? [host] : [], is_default: environments.length === 0 })
  }

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label="环境配置">
      <button className="modal-scrim" onClick={onClose} aria-label="关闭" type="button" />
      <form className="modal-card environment-modal" onSubmit={(event) => void submit(event)}>
        <header><div><h2>{project.name} · 环境配置</h2><p>Secret 仅保存操作系统环境变量名，不进入数据库或报告。</p></div><button className="icon-button" onClick={onClose} type="button"><X size={18} /></button></header>
        <div className="environment-list">{environments.map((item) => <div key={item.id}><strong>{item.name}</strong><span>{item.kind} · {item.base_url || '未配置 Base URL'}</span><small>{item.auth_type === 'none' ? '无认证' : `${item.auth_type} / ${item.secret_ref}`}</small></div>)}</div>
        <div className="form-grid">
          <label>环境名称<input value={name} onChange={(event) => setName(event.target.value)} required placeholder="集成测试环境" /></label>
          <label>环境类型<select value={kind} onChange={(event) => setKind(event.target.value)}><option value="local">Local</option><option value="dev">Dev</option><option value="test">Test</option><option value="staging">Staging</option><option value="production">Production</option></select></label>
          <label className="span-2">Base URL<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} type="url" placeholder="https://api.example.com" /></label>
          <label>认证方式<select value={authType} onChange={(event) => setAuthType(event.target.value as EnvironmentItem['auth_type'])}><option value="none">无认证</option><option value="bearer">Bearer Token</option><option value="api_key">API Key</option><option value="static_header">静态 Header</option></select></label>
          <label>Secret 环境变量<input value={secretRef} onChange={(event) => setSecretRef(event.target.value.toUpperCase())} pattern="[A-Z][A-Z0-9_]*" disabled={authType === 'none'} placeholder="TEST_API_TOKEN" /></label>
        </div>
        <footer><button className="button secondary" onClick={onClose} type="button">关闭</button><button className="button primary" type="submit">添加环境</button></footer>
      </form>
    </div>
  )
}
