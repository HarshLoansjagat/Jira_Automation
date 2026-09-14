import { useEffect, useMemo, useState } from 'react'
import api from '../api/client'

interface QAMember {
  name: string
  assigned_sp: number
  completed_sp: number
  remaining_sp: number
  completion_pct: number
  task_count: number
  completed_task_count: number
}

interface QATask {
  issue_key: string
  parent_key?: string | null
  summary: string
  status: string
  owner?: string | null
  story_points: number
  completed_sp: number
  remaining_sp: number
}

interface Snapshot {
  sprint: string
  snapshot_date: string
  snapshot_type: string
  overall_scope: number
  qa: { total_sp: number; completed_sp: number; members: QAMember[] }
  tasks: QATask[]
}

const number = (value: number) => value.toFixed(2)

export default function QA() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [selectedMember, setSelectedMember] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/reports/snapshots')
      .then(({ data }) => {
        const latest = data?.[0]
        if (!latest) return
        return api.get(`/reports/snapshots/${latest.id}`)
      })
      .then((response) => response && setSnapshot(response.data))
      .catch(() => setError('Unable to load persisted QA snapshots.'))
      .finally(() => setLoading(false))
  }, [])

  const tasks = useMemo(
    () => snapshot?.tasks.filter((task) => !selectedMember || task.owner === selectedMember) ?? [],
    [snapshot, selectedMember],
  )

  if (loading) return <div className="card">Loading QA history...</div>
  if (error) return <div className="card text-red-700">{error}</div>
  if (!snapshot) return <div className="card"><h1 className="text-2xl font-bold">QA</h1><p className="mt-2 text-gray-600">No persisted QA snapshot yet. Upload a Jira CSV to begin.</p></div>

  const qaCompletion = snapshot.qa.total_sp ? snapshot.qa.completed_sp / snapshot.qa.total_sp * 100 : 0
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm uppercase tracking-wide text-gray-500">{snapshot.snapshot_type} · {snapshot.snapshot_date}</p>
        <h1 className="text-3xl font-bold text-gray-900">QA reporting</h1>
        <p className="text-gray-600">{snapshot.sprint} · persisted snapshot</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="card"><p className="text-sm text-gray-500">QA tasks</p><p className="text-2xl font-bold">{snapshot.tasks.length}</p></div>
        <div className="card"><p className="text-sm text-gray-500">Total QA SP</p><p className="text-2xl font-bold">{number(snapshot.qa.total_sp)}</p></div>
        <div className="card"><p className="text-sm text-gray-500">Completed</p><p className="text-2xl font-bold">{number(snapshot.qa.completed_sp)}</p></div>
        <div className="card"><p className="text-sm text-gray-500">Remaining</p><p className="text-2xl font-bold">{number(snapshot.qa.total_sp - snapshot.qa.completed_sp)}</p></div>
        <div className="card"><p className="text-sm text-gray-500">Completion</p><p className="text-2xl font-bold">{qaCompletion.toFixed(2)}%</p></div>
      </div>
      <div className="card overflow-x-auto">
        <h2 className="text-xl font-semibold mb-4">QA members</h2>
        <table className="min-w-full text-sm">
          <thead><tr className="bg-gray-100 text-left"><th className="px-3 py-3">QA member</th><th className="px-3 py-3">Assigned SP</th><th className="px-3 py-3">Completed SP</th><th className="px-3 py-3">Remaining SP</th><th className="px-3 py-3">Completion</th><th className="px-3 py-3">Tasks</th></tr></thead>
          <tbody>{snapshot.qa.members.map((member) => <tr key={member.name} className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => setSelectedMember(selectedMember === member.name ? '' : member.name)}><td className="px-3 py-3 font-medium">{member.name}</td><td className="px-3 py-3">{number(member.assigned_sp)}</td><td className="px-3 py-3">{number(member.completed_sp)}</td><td className="px-3 py-3">{number(member.remaining_sp)}</td><td className="px-3 py-3">{member.completion_pct.toFixed(2)}%</td><td className="px-3 py-3">{member.completed_task_count}/{member.task_count}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card overflow-x-auto">
        <div className="flex items-center justify-between gap-3 mb-4"><h2 className="text-xl font-semibold">QA task explorer</h2><select value={selectedMember} onChange={(event) => setSelectedMember(event.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm"><option value="">All members</option>{snapshot.qa.members.map((member) => <option key={member.name}>{member.name}</option>)}</select></div>
        <table className="min-w-full text-sm"><thead><tr className="bg-gray-100 text-left"><th className="px-3 py-3">Issue</th><th className="px-3 py-3">Parent</th><th className="px-3 py-3">Summary</th><th className="px-3 py-3">Owner</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">SP</th><th className="px-3 py-3">Completed</th><th className="px-3 py-3">Remaining</th></tr></thead><tbody>{tasks.map((task) => <tr key={task.issue_key} className="border-t"><td className="px-3 py-3 font-medium">{task.issue_key}</td><td className="px-3 py-3">{task.parent_key || '-'}</td><td className="px-3 py-3">{task.summary}</td><td className="px-3 py-3">{task.owner || '-'}</td><td className="px-3 py-3">{task.status}</td><td className="px-3 py-3">{number(task.story_points)}</td><td className="px-3 py-3">{number(task.completed_sp)}</td><td className="px-3 py-3">{number(task.remaining_sp)}</td></tr>)}</tbody></table>
      </div>
    </div>
  )
}