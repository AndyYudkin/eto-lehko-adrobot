import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireAuth } from './components/RequireAuth';
import { Campaigns } from './pages/Campaigns';
import { Editor } from './pages/Editor';
import { Login } from './pages/Login';
import { Logout } from './pages/Logout';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/logout" element={<Logout />} />
      <Route
        path="/campaigns"
        element={
          <RequireAuth>
            <Campaigns />
          </RequireAuth>
        }
      />
      <Route
        path="/campaigns/:id"
        element={
          <RequireAuth>
            <Editor />
          </RequireAuth>
        }
      />
      <Route path="/" element={<Navigate to="/campaigns" replace />} />
    </Routes>
  );
}
