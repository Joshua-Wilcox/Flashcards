import { Routes, Route, Navigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from './api/client';
import Layout from './components/Layout';
import Home from './pages/Home';
import Leaderboard from './pages/Leaderboard';
import Stats from './pages/Stats';
import SubmitFlashcard from './pages/SubmitFlashcard';
import Admin from './pages/Admin';
import PDFs from './pages/PDFs';
import PDFManagement from './pages/PDFManagement';

export default function App() {
  const { data: user, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: api.getMe,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-blue-600 border-t-transparent"></div>
      </div>
    );
  }

  return (
    <Layout user={user}>
      <Routes>
        <Route path="/" element={<Home user={user} />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/stats" element={user?.authenticated ? <Stats /> : <Navigate to="/" />} />
        <Route path="/stats/:userId" element={<Stats />} />
        <Route 
          path="/submit" 
          element={user?.authenticated ? <SubmitFlashcard /> : <Navigate to="/" />} 
        />
        <Route 
          path="/admin" 
          element={user?.is_admin ? <Admin /> : <Navigate to="/" />} 
        />
        <Route
          path="/pdfs"
          element={(user?.is_whitelisted || user?.is_admin) ? <PDFs user={user} /> : <Navigate to="/" />}
        />
        <Route
          path="/admin/pdfs"
          element={user?.is_admin ? <PDFManagement /> : <Navigate to="/" />}
        />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  );
}
