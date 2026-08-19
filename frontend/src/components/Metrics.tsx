import { Box, ClipboardCheck, FileCheck2, UserRoundSearch } from 'lucide-react'

interface MetricsProps {
  values: {
    requirement_coverage: number
    api_coverage: number
    scenario_pass_rate: number
    pending_reviews: number
  }
}

const definitions = [
  { key: 'requirement_coverage', label: '需求覆盖率', tone: 'blue', icon: FileCheck2, suffix: '%' },
  { key: 'api_coverage', label: 'API 覆盖率', tone: 'green', icon: Box, suffix: '%' },
  { key: 'scenario_pass_rate', label: '场景通过率', tone: 'violet', icon: ClipboardCheck, suffix: '%' },
  { key: 'pending_reviews', label: '待审核', tone: 'amber', icon: UserRoundSearch, suffix: '' },
] as const

export function Metrics({ values }: MetricsProps) {
  return (
    <section className="metrics-grid" aria-label="项目关键指标">
      {definitions.map(({ key, label, tone, icon: Icon, suffix }) => {
        const value = values[key]
        return (
          <article className={`metric metric-${tone}`} key={key}>
            <div className="metric-icon"><Icon size={21} /></div>
            <div className="metric-body">
              <div className="metric-label">{label}</div>
              <div className="metric-value">{value}<small>{suffix}</small></div>
              {suffix ? (
                <div className="metric-progress" aria-label={`${label} ${value}%`}>
                  <span style={{ width: `${value}%` }} />
                </div>
              ) : (
                <div className="metric-hint">实时待处理数量</div>
              )}
            </div>
          </article>
        )
      })}
    </section>
  )
}
