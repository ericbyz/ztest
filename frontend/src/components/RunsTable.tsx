import { CheckCircle2, CircleX, ExternalLink } from 'lucide-react'
import type { Run } from '../types'

interface RunsTableProps {
  runs: Run[]
  onSelect: (run: Run) => void
}

function formatDuration(milliseconds: number) {
  const totalSeconds = Math.round(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  return `${String(minutes).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

export function RunsTable({ runs, onSelect }: RunsTableProps) {
  return (
    <section className="panel runs-panel">
      <div className="panel-heading">
        <div>
          <h2>最近执行</h2>
        </div>
        <button className="link-button" type="button">查看全部 <ExternalLink size={14} /></button>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>执行时间</th>
              <th>场景名称</th>
              <th>环境</th>
              <th>结果</th>
              <th>通过率</th>
              <th>耗时</th>
              <th>触发人</th>
            </tr>
          </thead>
          <tbody>
            {runs.slice(0, 5).map((run) => (
              <tr key={run.id} onClick={() => onSelect(run)}>
                <td className="muted-cell">{formatTime(run.started_at)}</td>
                <td className="scenario-cell">{run.scenario_name}</td>
                <td><span className="env-label">{run.environment.toUpperCase()}</span></td>
                <td>
                  <span className={`status ${run.status}`}>
                    {run.status === 'passed' ? <CheckCircle2 size={14} /> : <CircleX size={14} />}
                    {run.status === 'passed' ? '通过' : '失败'}
                  </span>
                </td>
                <td>
                  <div className={`rate ${run.status}`}><span style={{ width: `${run.pass_rate}%` }} /></div>
                  <small>{run.pass_rate}%</small>
                </td>
                <td className="muted-cell">{formatDuration(run.duration_ms)}</td>
                <td className="muted-cell">{run.trigger === 'manual' ? '张三' : '定时任务'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
