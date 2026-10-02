import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import ManagementLayout from './pages/ManagementLayout';
import CoursePage from './pages/CoursePage';
import RosterPage from './pages/RosterPage';
import QuestionEditorPage from './pages/QuestionEditorPage';
import GameLayout from './pages/game/GameLayout';
import LobbyPage from './pages/game/LobbyPage';
import QuestionPage from './pages/game/QuestionPage';
import ResultsPage from './pages/game/ResultsPage';
import GameOverPage from './pages/game/GameOverPage';

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!localStorage.getItem('token')) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* Non-game pages share the management top bar (T4 §6.3). */}
        <Route element={<RequireAuth><ManagementLayout /></RequireAuth>}>
          <Route path="/home" element={<HomePage />} />
          <Route path="/courses/:courseId" element={<CoursePage />} />
          <Route path="/courses/:courseId/roster" element={<RosterPage />} />
          <Route path="/games/:gameId/edit" element={<QuestionEditorPage />} />
        </Route>
        <Route path="/game/:code" element={<RequireAuth><GameLayout /></RequireAuth>}>
          <Route path="lobby" element={<LobbyPage />} />
          <Route path="question" element={<QuestionPage />} />
          <Route path="results" element={<ResultsPage />} />
          <Route path="gameover" element={<GameOverPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
