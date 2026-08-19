import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';

const ProtectedLayout: React.FC<{
  token: string | null;
  onLogout: () => void;
}> = ({ token, onLogout }) => {
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  let activeNav: 'dashboard' | 'observability' | 'dlq' | 'connections' | 'studio' | 'bulk' | 'settings' | 'docs' = 'dashboard';
  if (location.pathname.startsWith('/observability')) activeNav = 'observability';
  else if (location.pathname.startsWith('/dlq')) activeNav = 'dlq';
  else if (location.pathname.startsWith('/connections')) activeNav = 'connections';
  else if (location.pathname.startsWith('/studio')) activeNav = 'studio';
  else if (location.pathname.startsWith('/bulk-import')) activeNav = 'bulk';
  else if (location.pathname.startsWith('/settings')) activeNav = 'settings';
  else if (location.pathname.startsWith('/docs')) activeNav = 'docs';

  return <Dashboard token={token} onLogout={onLogout} initialNav={activeNav} />;
};

export const App: React.FC = () => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('etl_token'));

  useEffect(() => {
    const savedToken = localStorage.getItem('etl_token');
    if (savedToken) {
      fetch('/auth/me', {
        headers: { Authorization: `Bearer ${savedToken}` },
      })
        .then((res) => {
          if (!res.ok) {
            handleLogout();
          } else {
            setToken(savedToken);
          }
        })
        .catch(() => {
          handleLogout();
        });
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('etl_token');
    setToken(null);
  };

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            token ? <Navigate to="/dashboard" replace /> : <Login onLoginSuccess={(newToken) => setToken(newToken)} />
          }
        />
        <Route
          path="/dashboard"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/observability"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/dlq"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/connections"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/studio"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/bulk-import"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/settings"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route
          path="/docs"
          element={<ProtectedLayout token={token} onLogout={handleLogout} />}
        />
        <Route path="*" element={<Navigate to={token ? "/dashboard" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
