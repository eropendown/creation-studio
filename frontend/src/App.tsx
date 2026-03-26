import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/shared/Layout'
import MangaStudio from './pages/MangaStudio'
import NovelStudio from './pages/NovelStudio'
import ConfigPanel from './pages/ConfigPanel'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/novel" replace />} />
          <Route path="novel"  element={<NovelStudio />} />
          <Route path="manga"  element={<MangaStudio />} />
          <Route path="config" element={<ConfigPanel />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
