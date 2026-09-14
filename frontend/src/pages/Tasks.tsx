import { useEffect, useState } from 'react'
import api from '../api/client'

interface Task {
  issue_key: string
  summary: string
  issue_type: string
  parent_key?: string | null
  status: string
  assignee?: string | null
  developer_owner?: string | null
  qa_owner?: string | null
  story_points?: number | null
  developer_sp?: number | null
  qa_sp?: number | null
  completed_sp: number
  remaining_sp: number
  sprint: string
  snapshot_type: string
  snapshot_date: string
}

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true)
      api.get('/reports/tasks', { params: { search: search || undefined, limit: 200 } })
        .then(({ data }) => { setTasks(data.tasks); setTotal(data.total) })
        .finally(() => setLoading(false))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  const exportCsv = () => {
    const headers = ['Issue Key', 'Summary', 'Status', 'Assignee', 'Developer SP', 'QA SP', 'Completed SP', 'Remaining SP']
    const lines = tasks.map((task) => [task.issue_key, task.summary, task.status, task.assignee || '', task.developer_sp ?? '', task.qa_sp ?? '', task.completed_sp, task.remaining_sp].map((value) => `"${String(value).replace(/"/g, '""')}"`).join(','))
    const blob = new Blob([[headers.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'jira-task-explorer.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-sm uppercase tracking-wide text-gray-500">Auditability</p><h1 className="text-3xl font-bold text-gray-900">Task Explorer</h1><p className="mt-1 text-gray-600">Every persisted issue used by sprint calculations.</p></div>
        <button onClick={exportCsv} disabled={!tasks.length} className="btn-secondary disabled:opacity-50">Export CSV</button>
      </div>
      <div className="card"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search issue key or summary..." className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm outline-none focus:border-brand-mid" /></div>
      <div className="card overflow-x-auto">
        <div className="mb-4 text-sm text-gray-500">{loading ? 'Loading persisted tasks...' : `${total} task${total === 1 ? '' : 's'} found`}</div>
        <table className="min-w-[1100px] w-full text-sm"><thead><tr className="bg-gray-100 text-left"><th className="px-3 py-3">Issue</th><th className="px-3 py-3">Summary</th><th className="px-3 py-3">Type</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">Assignee</th><th className="px-3 py-3">Dev SP</th><th className="px-3 py-3">QA SP</th><th className="px-3 py-3">Completed</th><th className="px-3 py-3">Remaining</th><th className="px-3 py-3">Snapshot</th></tr></thead><tbody>{tasks.map((task) => <tr key={`${task.snapshot_type}-${task.snapshot_date}-${task.issue_key}`} className="border-t hover:bg-gray-50"><td className="px-3 py-3 font-semibold text-brand-mid">{task.issue_key}</td><td className="max-w-xs px-3 py-3">{task.summary}</td><td className="px-3 py-3">{task.issue_type || '-'}</td><td className="px-3 py-3">{task.status || '-'}</td><td className="px-3 py-3">{task.assignee || '-'}</td><td className="px-3 py-3">{task.developer_sp ?? '-'}</td><td className="px-3 py-3">{task.qa_sp ?? '-'}</td><td className="px-3 py-3">{task.completed_sp.toFixed(2)}</td><td className="px-3 py-3">{task.remaining_sp.toFixed(2)}</td><td className="px-3 py-3 whitespace-nowrap">{task.snapshot_type} · {task.snapshot_date}</td></tr>)}</tbody></table>
        {!loading && tasks.length === 0 && <p className="py-12 text-center text-gray-500">No persisted tasks match this search.</p>}
      </div>
    </div>
  )
}