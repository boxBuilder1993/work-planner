import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { TasksProvider } from './hooks/useTasks';
import SignIn from './components/SignIn';
import TaskList from './components/TaskList';
import TaskDetail from './components/TaskDetail';
import Settings from './components/Settings';
import { SimulationForm } from './components/SimulationForm';
import { Header } from './components/Header';
import ChatPanel from './components/ChatPanel';
import styles from './components/AppLayout.module.css';

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <div className={styles.container}>
        <div className={styles.content}>
          {children}
        </div>
        <div className={styles.chatPanelWrapper}>
          <ChatPanel />
        </div>
      </div>
    </>
  );
}

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

  return <AppLayout>{children}</AppLayout>;
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
      <Route
        path="/simulate"
        element={
          <AuthGuard>
            <SimulationForm />
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
