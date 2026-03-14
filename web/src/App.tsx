import { useState, useEffect, useRef } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth, needsInitialRestore, clearInitialRestore } from './auth/AuthContext';
import { TasksProvider, useTasks } from './hooks/useTasks';
import { useAutoSync } from './hooks/useAutoSync';
import { performRestore } from './backup/backupProcessor';
import { UnauthorizedError } from './drive/driveApi';
import SignIn from './components/SignIn';
import TaskList from './components/TaskList';
import TaskDetail from './components/TaskDetail';
import Settings from './components/Settings';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const taskStore = useTasks();
  const [restoring, setRestoring] = useState(() => needsInitialRestore());
  const startedRef = useRef(false);
  useAutoSync();

  useEffect(() => {
    if (startedRef.current || !needsInitialRestore()) return;
    if (!auth.isSignedIn || !auth.encryptionKey) return;

    startedRef.current = true;
    clearInitialRestore();

    performRestore(auth.getToken(), auth.encryptionKey)
      .then((restored) => {
        taskStore.loadFromRestore(restored.tasks, restored.comments, restored.repeatingTasks);
      })
      .catch((err) => {
        if (err instanceof UnauthorizedError) {
          auth.handleUnauthorized();
        }
      })
      .finally(() => setRestoring(false));
  }, [auth, taskStore]);

  if (auth.isLoading || restoring) {
    return (
      <div className="center-content">
        <div className="spinner spinner-large" />
      </div>
    );
  }

  if (!auth.isSignedIn || !auth.encryptionKey) {
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
