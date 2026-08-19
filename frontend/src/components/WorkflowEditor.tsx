import {
  Braces,
  Check,
  ChevronRight,
  CircleDot,
  Copy,
  Play,
  Save,
  Settings2,
  ShieldCheck,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Scenario, TestStep } from '../types'

interface WorkflowEditorProps {
  scenario: Scenario
  running: boolean
  onRun: () => void
  onApprove: () => void
  onSave: (ir: Scenario['ir']) => Promise<void>
  mode: 'simulated' | 'live'
  onModeChange: (mode: 'simulated' | 'live') => void
}

function Method({ method }: { method: string }) {
  return <span className={`method method-${method.toLowerCase()}`}>{method}</span>
}

function StepCard({ step, index, selected, onSelect }: { step: TestStep; index: number; selected: boolean; onSelect: () => void }) {
  const input = JSON.stringify(step.input, null, 2)
    .replace(/[{}",]/g, '')
    .trim()
    .split('\n')
    .slice(0, 4)
  return (
    <button className={`step-card ${selected ? 'selected' : ''}`} onClick={onSelect} type="button">
      <div className="step-head">
        <span className="step-number">{index + 1}</span>
        <strong>{step.operation_id}</strong>
        <Method method={step.method} />
      </div>
      <div className="step-path">{step.path}</div>
      <div className="step-section">
        <label>请求参数</label>
        <pre>{input.join('\n') || '—'}</pre>
      </div>
      {Object.keys(step.extract).length > 0 ? (
        <div className="step-section extract">
          <label>提取数据</label>
          {Object.entries(step.extract).map(([key, value]) => <code key={key}>{key} ← {value}</code>)}
        </div>
      ) : null}
      <div className="step-actions"><Copy size={14} /><Trash2 size={14} /></div>
    </button>
  )
}

export function WorkflowEditor({ scenario, running, onRun, onApprove, onSave, mode, onModeChange }: WorkflowEditorProps) {
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, scenario.ir.steps.length - 1))
  const [tab, setTab] = useState<'flow' | 'yaml'>('flow')
  const [irText, setIrText] = useState(() => JSON.stringify(scenario.ir, null, 2))
  const [editError, setEditError] = useState('')
  const selected = scenario.ir.steps[selectedIndex] ?? scenario.ir.steps[0]
  const requirementAssertion = useMemo(
    () => selected?.assertions.find((item) => item.source === 'requirement'),
    [selected],
  )
  const saveIr = async () => {
    try {
      const parsed = JSON.parse(irText) as Scenario['ir']
      setEditError('')
      await onSave(parsed)
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'Test IR 不是有效 JSON')
    }
  }

  return (
    <section className="workflow-panel" id="scenario-editor">
      <div className="workflow-header">
        <div className="workflow-title">
          <h2>场景编辑器：{scenario.name}</h2>
          <span className="saved"><Check size={13} /> 已保存</span>
          <span className={`review-state ${scenario.status}`}>{scenario.status === 'approved' ? '已审核' : '草稿'}</span>
        </div>
        <div className="workflow-actions">
          <div className="view-tabs">
            <button className={tab === 'flow' ? 'active' : ''} onClick={() => setTab('flow')} type="button">流程</button>
            <button className={tab === 'yaml' ? 'active' : ''} onClick={() => setTab('yaml')} type="button">Test IR</button>
          </div>
          <select className="run-mode" value={mode} onChange={(event) => onModeChange(event.target.value as 'simulated' | 'live')} aria-label="执行模式"><option value="simulated">模拟执行</option><option value="live">真实执行</option></select>
          <button className="button secondary" type="button"><Settings2 size={15} /> 场景配置</button>
          <button className="button secondary" onClick={() => void saveIr()} type="button"><Save size={15} /> 保存</button>
          <button className="button primary" onClick={onRun} disabled={running} type="button">
            <Play size={15} fill="currentColor" /> {running ? '执行中…' : '运行'}
          </button>
          <button className="button outline" onClick={onApprove} type="button"><ShieldCheck size={15} /> 提交评审</button>
        </div>
      </div>
      {scenario.validation_errors.length > 0 ? (
        <div className="validation-strip">静态校验发现 {scenario.validation_errors.length} 个问题：{scenario.validation_errors[0]}</div>
      ) : null}
      {tab === 'yaml' ? (
        <div className="ir-editor"><textarea aria-label="Test IR JSON" value={irText} onChange={(event) => setIrText(event.target.value)} spellCheck={false} />{editError ? <div className="editor-error">{editError}</div> : null}</div>
      ) : (
        <div className="workflow-body">
          <div className="tool-rail">
            <button type="button"><span>＋</span> 添加步骤</button>
            <button type="button"><CircleDot size={15} /> 接口调用</button>
            <button type="button"><GitBranchIcon /> 条件分支</button>
            <button type="button"><Braces size={15} /> 断言校验</button>
          </div>
          <div className="workflow-canvas">
            <div className="dot-grid" />
            <div className="steps-row">
              {scenario.ir.steps.map((step, index) => (
                <div className="step-with-connector" key={step.id}>
                  <StepCard
                    step={step}
                    index={index}
                    selected={selectedIndex === index}
                    onSelect={() => setSelectedIndex(index)}
                  />
                  {index < scenario.ir.steps.length - 1 ? (
                    <div className="connector"><span>{Object.keys(step.extract)[0] ?? 'next'}</span><ChevronRight size={17} /></div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
          <aside className="inspector">
            <div className="inspector-head"><span>步骤 {selectedIndex + 1}</span><strong>{selected?.operation_id}</strong></div>
            <div className="form-field">
              <label>断言类型</label>
              <select defaultValue={requirementAssertion ? 'expression' : 'status'}>
                <option value="expression">数值比较</option>
                <option value="status">状态码</option>
              </select>
            </div>
            <div className="form-field">
              <label>表达式</label>
              <input defaultValue={String(requirementAssertion?.expression ?? '$.response.status')} />
            </div>
            <div className="form-field">
              <label>比较方式</label>
              <select defaultValue="equals"><option value="equals">等于</option><option value="contains">包含</option></select>
            </div>
            <div className="form-field">
              <label>期望值</label>
              <input defaultValue={requirementAssertion ? '${initial_stock - 2}' : '200'} />
            </div>
            {requirementAssertion ? <div className="source-proof"><ShieldCheck size={15} /> 来源：{String(requirementAssertion.requirement_ref ?? '未关联')} · 置信度 {Math.round(Number(requirementAssertion.confidence ?? scenario.confidence) * 100)}%</div> : null}
          </aside>
        </div>
      )}
    </section>
  )
}

function GitBranchIcon() {
  return <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M6 3v12a3 3 0 0 0 3 3h9M6 8h7a3 3 0 0 0 3-3V3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /><circle cx="6" cy="3" r="2" stroke="currentColor" strokeWidth="2" /><circle cx="18" cy="19" r="2" stroke="currentColor" strokeWidth="2" /></svg>
}
