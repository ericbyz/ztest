import {
  Boxes,
  FileText,
  FlaskConical,
  Gauge,
  GitFork,
  ListChecks,
  Settings,
  Users,
} from 'lucide-react'
import type { ComponentType } from 'react'
import type { NavKey } from '../types'

interface SidebarProps {
  active: NavKey
  onNavigate: (key: NavKey) => void
  open: boolean
  onClose: () => void
}

const navItems: Array<{ key: NavKey; label: string; icon: ComponentType<{ size?: number }> }> = [
  { key: 'overview', label: '项目总览', icon: Gauge },
  { key: 'documents', label: '文档中心', icon: FileText },
  { key: 'requirements', label: '需求中心', icon: ListChecks },
  { key: 'api', label: 'API 图谱', icon: GitFork },
  { key: 'scenarios', label: '场景编辑器', icon: FlaskConical },
  { key: 'reports', label: '执行与报告', icon: Boxes },
]

export function Sidebar({ active, onNavigate, open, onClose }: SidebarProps) {
  const select = (key: NavKey) => {
    onNavigate(key)
    onClose()
  }

  return (
    <>
      <div className={`sidebar-scrim ${open ? 'visible' : ''}`} onClick={onClose} />
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">AI</div>
          <span>AI Test Tool</span>
        </div>
        <nav aria-label="主导航">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              className={`nav-item ${active === key ? 'active' : ''}`}
              onClick={() => select(key)}
              type="button"
            >
              <Icon size={19} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-item" type="button">
            <Users size={19} />
            <span>QA 团队</span>
          </button>
          <button className="nav-item" type="button">
            <Settings size={19} />
            <span>系统设置</span>
          </button>
        </div>
      </aside>
    </>
  )
}

