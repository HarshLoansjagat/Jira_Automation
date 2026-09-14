import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import History from './pages/History'
import ReportDetail from './pages/ReportDetail'
import DevelopersPage from './pages/Developers'
import SettingsPage from './pages/Settings'
import QA from './pages/QA'
import Tasks from './pages/Tasks'
import SprintHistory from './pages/SprintHistory'
import Analytics from './pages/Analytics'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/history" element={<History />} />
        <Route path="/reports/:id" element={<ReportDetail />} />
        <Route path="/developers" element={<DevelopersPage />} />
        <Route path="/qa" element={<QA />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/sprint-history" element={<SprintHistory />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  )
}
