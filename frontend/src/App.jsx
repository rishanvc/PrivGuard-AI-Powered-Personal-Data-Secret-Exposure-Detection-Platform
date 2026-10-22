import { Route, Routes } from 'react-router-dom'

import RequireAuth from './auth/RequireAuth'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import NewScan from './pages/NewScan'
import Placeholder from './pages/Placeholder'
import ScanDetail from './pages/ScanDetail'
import Scans from './pages/Scans'

/**
 * Routes mirror the screens in SRS 5.1.
 * Everything except /login sits behind RequireAuth.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="scans" element={<Scans />} />
        <Route path="scans/new" element={<NewScan />} />
        <Route path="scans/:scanId" element={<ScanDetail />} />
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
