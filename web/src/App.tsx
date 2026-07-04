import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { TasksProvider } from './hooks/useTasks';
import SignIn from './components/SignIn';
import AppShell from './components/AppShell';
import Home from './components/Home';
import ProjectView from './components/ProjectView';
import Schedule from './components/Schedule';
import TaskList from './components/TaskList';
import TaskDetail from './components/TaskDetail';
import Settings from './components/Settings';
import KnowledgeCards from './components/KnowledgeCards';
import Planner from './components/Planner';

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

function Soon({ title }: { title: string }) {
  return (
    <div className="p-7">
      <h1 className="text-[19px] font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">Coming soon.</p>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/auth" element={<AuthRedirect />} />
      <Route path="/" element={<AuthGuard><Home /></AuthGuard>} />
      <Route path="/projects/:taskId" element={<AuthGuard><ProjectView /></AuthGuard>} />
      <Route path="/schedule" element={<AuthGuard><Schedule /></AuthGuard>} />
      <Route path="/team" element={<AuthGuard><Soon title="Team & Calendar" /></AuthGuard>} />
      <Route path="/search" element={<AuthGuard><Soon title="Search" /></AuthGuard>} />
      <Route path="/tasks" element={<AuthGuard><TaskList /></AuthGuard>} />
      <Route path="/tasks/new" element={<AuthGuard><TaskDetail /></AuthGuard>} />
      <Route path="/tasks/:taskId" element={<AuthGuard><TaskDetail /></AuthGuard>} />
      <Route path="/settings" element={<AuthGuard><Settings /></AuthGuard>} />
      <Route path="/knowledge" element={<AuthGuard><KnowledgeCards /></AuthGuard>} />
      <Route path="/planner" element={<AuthGuard><Planner /></AuthGuard>} />
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
