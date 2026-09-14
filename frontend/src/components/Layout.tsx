import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Upload, History, Users, Settings, BarChart3, FlaskConical, ListChecks, Clock3, Activity } from 'lucide-react'
import type { ReactNode } from 'react'

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/upload',    icon: Upload,          label: 'Upload CSV' },
  { to: '/history',   icon: History,         label: 'Reports' },
  { to: '/developers',icon: Users,           label: 'Developers' },
  { to: '/qa',        icon: FlaskConical,    label: 'QA' },
  { to: '/tasks',     icon: ListChecks,      label: 'Tasks' },
  { to: '/sprint-history', icon: Clock3,     label: 'Sprint History' },
  { to: '/analytics',  icon: Activity,       label: 'Analytics' },
  { to: '/settings',  icon: Settings,        label: 'Settings' },
]

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-brand-dark text-white flex flex-col flex-shrink-0">
        {/* Logo */}
        <div className="px-6 py-5 border-b border-blue-800">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-blue-300" />
            <div>
              <p className="font-bold text-lg leading-none">DC-AI</p>
              <p className="text-xs text-blue-300 mt-0.5">Sprint Reporting</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-mid text-white'
                    : 'text-blue-200 hover:bg-blue-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-6 py-4 border-t border-blue-800 text-xs text-blue-400">
          v1.0.0 · DC-AI Project
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-8">{children}</div>
      </main>
    </div>
  )
}
