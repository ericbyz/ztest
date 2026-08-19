interface CoverageRadarProps {
  data: Array<{ module: string; requirements: number; api: number }>
}

const center = 130
const radius = 88

function point(index: number, value: number, total: number) {
  const angle = -Math.PI / 2 + (index * Math.PI * 2) / total
  const distance = radius * (value / 100)
  return `${center + Math.cos(angle) * distance},${center + Math.sin(angle) * distance}`
}

export function CoverageRadar({ data }: CoverageRadarProps) {
  const requirements = data.map((item, index) => point(index, item.requirements, data.length)).join(' ')
  const api = data.map((item, index) => point(index, item.api, data.length)).join(' ')
  const outer = data.map((_, index) => point(index, 100, data.length)).join(' ')

  return (
    <section className="panel coverage-panel">
      <div className="panel-heading compact">
        <div>
          <h2>覆盖率概览</h2>
        </div>
        <select aria-label="覆盖率维度" defaultValue="module"><option value="module">按模块</option></select>
      </div>
      <div className="radar-wrap">
        <svg className="radar" viewBox="0 0 260 260" role="img" aria-label="模块覆盖率雷达图">
          {[20, 40, 60, 80, 100].map((level) => (
            <polygon className="radar-grid" points={data.map((_, index) => point(index, level, data.length)).join(' ')} key={level} />
          ))}
          {data.map((_, index) => (
            <line key={index} className="radar-axis" x1={center} y1={center} x2={outer.split(' ')[index].split(',')[0]} y2={outer.split(' ')[index].split(',')[1]} />
          ))}
          <polygon className="radar-requirements" points={requirements} />
          <polygon className="radar-api" points={api} />
          {data.map((item, index) => {
            const [x, y] = point(index, 122, data.length).split(',').map(Number)
            return <text key={item.module} x={x} y={y} textAnchor="middle">{item.module}</text>
          })}
        </svg>
        <div className="radar-legend"><span className="req" />需求覆盖率 <span className="api" />API 覆盖率</div>
      </div>
    </section>
  )
}
