import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { TasksProvider } from './hooks/useTasks';
import SignIn from './components/SignIn';
import AppShell from './components/AppShell';
import Home from './components/Home';
import ProjectView from './components/ProjectView';
import Schedule from './components/Schedule';
import Team from './components/Team';
import Search from './components/Search';
import TaskDetail from './components/TaskDetail';
import Settings from './components/Settings';
import KnowledgeCards from './components/KnowledgeCards';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  if (auth.isLoading) {
    return (
      <div className="center-content">
        <div className="spinner spinner-large" />
      </div>
    );
  }
  if (!auth.isSignedIn) {
    return <Navigate to="/auth" replace />;
  }
  return <AppShell>{children}</AppShell>;
}

function AuthRedirect() {
  const { isSignedIn, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="center-content">
        <div className="spinner spinner-large" />
      </div>
    );
  }
  if (isSignedIn) {
    return <Navigate to="/" replace />;
  }
  return <SignIn />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/auth" element={<AuthRedirect />} />
      <Route path="/" element={<AuthGuard><Home /></AuthGuard>} />
      <Route path="/projects/:taskId" element={<AuthGuard><ProjectView /></AuthGuard>} />
      <Route path="/schedule" element={<AuthGuard><Schedule /></AuthGuard>} />
      <Route path="/team" element={<AuthGuard><Team /></AuthGuard>} />
      <Route path="/search" element={<AuthGuard><Search /></AuthGuard>} />
      {/* Legacy task list retired — Home (projects) + Search replace it. */}
      <Route path="/tasks" element={<Navigate to="/" replace />} />
      <Route path="/planner" element={<Navigate to="/" replace />} />
      <Route path="/tasks/new" element={<AuthGuard><TaskDetail /></AuthGuard>} />
      <Route path="/tasks/:taskId" element={<AuthGuard><TaskDetail /></AuthGuard>} />
      <Route path="/settings" element={<AuthGuard><Settings /></AuthGuard>} />
      <Route path="/knowledge" element={<AuthGuard><KnowledgeCards /></AuthGuard>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <TasksProvider>
        <AppRoutes />
      </TasksProvider>
    </AuthProvider>
  );
}
