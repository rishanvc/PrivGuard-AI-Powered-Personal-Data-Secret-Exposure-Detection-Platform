import { Route, Routes } from 'react-router-dom'

import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Placeholder from './pages/Placeholder'

/** Routes mirror the screens in SRS 5.1. */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route
          path="scans"
          element={<Placeholder title="Scans" cycle="3" description="Create scans and track their progress." />}
        />
        <Route
          path="findings"
          element={<Placeholder title="Findings" cycle="5" description="Review detected sensitive information." />}
        />
        <Route
          path="reports"
          element={<Placeholder title="Reports" cycle="11" description="Generate and export scan reports." />}
        />
        <Route
          path="settings"
          element={<Placeholder title="Settings" cycle="12" description="Scan limits, detection policies, and AI configuration." />}
        />
        <Route
          path="*"
          element={<Placeholder title="Not found" cycle="—" description="That page does not exist." />}
        />
      </Route>
    </Routes>
  )
}
