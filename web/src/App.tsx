import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { TasksProvider } from './hooks/useTasks';
import SignIn from './components/SignIn';
import TaskList from './components/TaskList';
import TaskDetail from './components/TaskDetail';
import Settings from './components/Settings';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isSignedIn, encryptionKey, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="center-content">
        <div className="spinner spinner-large" />
      </div>
    );
  }

  if (!isSignedIn || !encryptionKey) {
    return <Navigate to="/auth" replace />;
  }

  return <>{children}</>;
}

function AuthRedirect() {
  const { isSignedIn, encryptionKey, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="center-content">
        <div className="spinner spinner-large" />
      </div>
    );
  }

  if (isSignedIn && encryptionKey) {
    return <Navigate to="/tasks" replace />;
  }

  return <SignIn />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/auth" element={<AuthRedirect />} />
      <Route
        path="/tasks"
        element={
          <AuthGuard>
            <TaskList />
          </AuthGuard>
        }
      />
      <Route
        path="/tasks/new"
        element={
          <AuthGuard>
            <TaskDetail />
          </AuthGuard>
        }
      />
      <Route
        path="/tasks/:taskId"
        element={
          <AuthGuard>
            <TaskDetail />
          </AuthGuard>
        }
      />
      <Route
        path="/settings"
        element={
          <AuthGuard>
            <Settings />
          </AuthGuard>
        }
      />
      <Route path="*" element={<Navigate to="/auth" replace />} />
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
