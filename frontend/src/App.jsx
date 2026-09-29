import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { FieldLayout, OfficeLayout } from './components/Layouts'
import { Loading } from './components/ui'
import { useAuth } from './context/AuthContext'
import Login from './pages/Login'
import Register from './pages/Register'

const Overview = lazy(() => import('./pages/Overview'))
const MapPage = lazy(() => import('./pages/MapPage'))
const OffsetPage = lazy(() => import('./pages/OffsetPage'))
const KnowledgePage = lazy(() => import('./pages/KnowledgePage'))
const TrackingPage = lazy(() => import('./pages/TrackingPage'))
const DrillersPage = lazy(() => import('./pages/DrillersPage'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const DataPage = lazy(() => import('./pages/DataPage'))
const DrillerPortal = lazy(() => import('./pages/DrillerPortal'))
const FieldHome = lazy(() => import('./pages/field/FieldHome'))
const FieldMap = lazy(() => import('./pages/field/FieldMap'))
const FieldWells = lazy(() => import('./pages/field/FieldWells'))
const FieldMe = lazy(() => import('./pages/field/FieldMe'))

function home(user) {
  if (user.role === 'driller') return user.driller_status === 'approved' ? '/field' : '/driller'
  return '/office'
}

function Protected({ roles, children }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to={home(user)} replace />
  return children
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={user ? <Navigate to={home(user)} replace /> : <Login />} />
        <Route path="/register" element={user ? <Navigate to={home(user)} replace /> : <Register />} />
        <Route path="/driller" element={<Protected roles={['driller']}><DrillerPortal /></Protected>} />
        <Route path="/field" element={<Protected><FieldLayout /></Protected>}>
          <Route index element={<FieldHome />} />
          <Route path="map" element={<FieldMap />} />
          <Route path="wells" element={<FieldWells />} />
          <Route path="me" element={<FieldMe />} />
        </Route>
        <Route path="/office" element={<Protected roles={['admin', 'engineer']}><OfficeLayout /></Protected>}>
          <Route index element={<Overview />} />
          <Route path="map" element={<MapPage />} />
          <Route path="offset" element={<OffsetPage />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="tracking" element={<TrackingPage />} />
          <Route path="drillers" element={<DrillersPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="data" element={<DataPage />} />
        </Route>
        <Route path="*" element={<Navigate to={user ? home(user) : '/login'} replace />} />
      </Routes>
    </Suspense>
  )
}
