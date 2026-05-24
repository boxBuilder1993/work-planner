import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import type { TaskEntity } from '../types';
import { useTasks } from '../hooks/useTasks';
import { formatDate, formatDateTime, isOverdue } from '../utils';
import BreadcrumbBar from './BreadcrumbBar';
import TaskForm from './TaskForm';
import TaskItem from './TaskItem';
import CommentSection from './CommentSection';
import PriorityBadge from './PriorityBadge';
import styles from './TaskDetail.module.css';

/**
 * Per-task working directory on the user's Mac (where the AI does filesystem
 * work — clones, builds, generated files). Surface the path here so the user
 * can `cd` into it. Click the chip to copy.
 */
function WorkspaceChip({ path }: { path: string }) {
  const [copied, setCopied] = useState(false);

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(path);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // navigator.clipboard can fail on non-secure contexts or older browsers.
      // No alert; user sees no copy indication and that's a clear-enough signal.
    }
  };

  return (
    <span
      className={`${styles.chip} ${styles.workspaceChip} ${copied ? styles.workspaceChipCopied : ''}`}
      onClick={onClick}
      title={copied ? 'Copied!' : 'Click to copy workspace path'}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          void onClick();
        }
      }}
    >
      <span className={styles.workspaceChipLabel}>Workspace:</span>
      {copied ? 'Copied!' : path}
    </span>
  );
}

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const {
    getTaskById,
    getBreadcrumbs,
    getChildTasks,
    createTask,
    updateTask,
    deleteTask,
    getRepeatingTaskForTask,
    setRepeatingTask,
    removeRepeatingTask,
    fetchRepeatingTask,
    refreshTask,
    refreshChildren,
  } = useTasks();

  const isNew = !taskId;
  const parentIdParam = searchParams.get('parentId');

  const existingTask = taskId ? getTaskById(taskId) : undefined;
  const existingRepeat = taskId ? getRepeatingTaskForTask(taskId) : undefined;
  const [isEditing, setIsEditing] = useState(isNew);
  const [error, setError] = useState<string | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<TaskEntity[]>([]);
  const [editRepeatInterval, setEditRepeatInterval] = useState<number | null>(
    existingRepeat?.intervalDays ?? null,
  );
  const [editRepeatStartDate, setEditRepeatStartDate] = useState<number | null>(
    existingRepeat?.startDate ?? null,
  );
  const [editedTask, setEditedTask] = useState<TaskEntity>(() =>
    existingTask ?? {
      id: '',
      parentId: parentIdParam ?? null,
      title: '',
      description: '',
      status: 'PENDING' as const,
      priority: 3,
      dueDate: null,
      taskDate: null,
      plannedTime: null,
      duration: null,
      aiEnabled: false,
      props: {},
      createdAt: 0,
      updatedAt: 0,
    },
  );

  // Reset state when route changes (e.g., create→view, or parent→new child)
  useEffect(() => {
    setError(null);
    if (taskId) {
      // Viewing/editing existing task
      setIsEditing(false);
      const task = getTaskById(taskId);
      if (task) setEditedTask(task);
      const repeat = getRepeatingTaskForTask(taskId);
      setEditRepeatInterval(repeat?.intervalDays ?? null);
      setEditRepeatStartDate(repeat?.startDate ?? null);
    } else {
      // Creating new task
      setIsEditing(true);
      setEditedTask({
        id: '',
        parentId: parentIdParam ?? null,
        title: '',
        description: '',
        status: 'PENDING',
        priority: 3,
        dueDate: null,
        taskDate: null,
        plannedTime: null,
        duration: null,
        aiEnabled: false,
        props: {},
        createdAt: 0,
        updatedAt: 0,
      });
      setEditRepeatInterval(null);
      setEditRepeatStartDate(null);
      setBreadcrumbs([]);
    }
  }, [taskId, parentIdParam, getTaskById, getRepeatingTaskForTask]);

  // Fetch breadcrumbs, children, and repeating task from API + auto-refresh every 10s
  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    const fetchData = () => {
      refreshTask(taskId);
      getBreadcrumbs(taskId).then((crumbs) => {
        if (!cancelled) setBreadcrumbs(crumbs);
      });
      refreshChildren(taskId);
    };
    fetchData();
    fetchRepeatingTask(taskId);
    const interval = setInterval(fetchData, 3_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [taskId, refreshTask, getBreadcrumbs, refreshChildren, fetchRepeatingTask]);

  const children = existingTask ? getChildTasks(existingTask.id) : [];
  const openChildren = children.filter((c) => c.status !== 'CLOSED');
  const closedChildren = children.filter((c) => c.status === 'CLOSED');

  const handleSave = async () => {
    if (!editedTask.title.trim()) {
      setError('Title is required');
      return;
    }

    // Check if trying to close with open children
    if (existingTask && editedTask.status === 'CLOSED') {
      const pendingChildren = children.filter((c) => c.status === 'PENDING');
      if (pendingChildren.length > 0) {
        setError(
          `Close all sub-tasks before closing this task (${pendingChildren.length} still open)`,
        );
        return;
      }
    }

    setError(null);

    if (isNew) {
      const created = await createTask({
        title: editedTask.title.trim(),
        description: editedTask.description,
        parentId: editedTask.parentId,
        priority: editedTask.priority,
        dueDate: editedTask.dueDate,
        plannedTime: editedTask.plannedTime,
        duration: editedTask.duration,
      });
      // Set repeating rule on newly created task
      if (editRepeatInterval && editRepeatInterval > 0) {
        // eslint-disable-next-line react-hooks/purity -- quarantined; tracked in task d4dfaff6
        await setRepeatingTask(created.id, editRepeatInterval, editRepeatStartDate ?? Date.now());
      }
      navigate(`/tasks/${created.id}`, { replace: true });
    } else {
      await updateTask({ ...editedTask, title: editedTask.title.trim() });
      // Update repeating rule
      if (editRepeatInterval && editRepeatInterval > 0) {
        await setRepeatingTask(
          existingTask!.id,
          editRepeatInterval,
          // eslint-disable-next-line react-hooks/purity -- quarantined; tracked in task d4dfaff6
          editRepeatStartDate ?? existingRepeat?.startDate ?? Date.now(),
        );
      } else if (existingRepeat) {
        await removeRepeatingTask(existingTask!.id);
      }
      setIsEditing(false);
    }
  };

  const handleDelete = async () => {
    if (!existingTask) return;
    const childCount = children.length;
    const message = childCount > 0
      ? `Delete this task and its ${childCount} sub-task(s)?`
      : 'Delete this task?';
    if (window.confirm(message)) {
      await deleteTask(existingTask.id);
      navigate(-1);
    }
  };

  const handleCancel = () => {
    if (isNew) {
      navigate(-1);
    } else {
      setEditedTask(existingTask!);
      setIsEditing(false);
      setError(null);
    }
  };

  const handleEdit = () => {
    setEditedTask(existingTask!);
    setEditRepeatInterval(existingRepeat?.intervalDays ?? null);
    setEditRepeatStartDate(existingRepeat?.startDate ?? null);
    setIsEditing(true);
    setError(null);
  };

  // If task not found (and not new)
  if (!isNew && !existingTask) {
    return (
      <div className={styles.page}>
        <div className={styles.topBar}>
          <button className={styles.backButton} onClick={() => navigate(-1)}>
            &larr;
          </button>
          <span className={styles.topBarTitle}>Task Not Found</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <button className={styles.backButton} onClick={() => navigate(-1)}>
          &larr;
        </button>
        <span className={styles.topBarTitle}>
          {isNew ? 'New Task' : existingTask?.title ?? 'Task'}
        </span>
        <div className={styles.topBarActions}>
          {isEditing ? (
            <>
              <button className={styles.actionButton} onClick={handleCancel}>
                Cancel
              </button>
              <button className={styles.actionButton} onClick={handleSave}>
                Save
              </button>
            </>
          ) : (
            <>
              <button className={styles.actionButton} onClick={handleEdit}>
                Edit
              </button>
              <button
                className={`${styles.actionButton} ${styles.deleteButton}`}
                onClick={handleDelete}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>

      <div className={styles.content}>
        {/* Breadcrumbs */}
        {breadcrumbs.length > 0 && <BreadcrumbBar breadcrumbs={breadcrumbs} />}

        {error && <div className={styles.error}>{error}</div>}

        {isEditing ? (
          <div className={styles.viewSection}>
            <TaskForm
              task={editedTask}
              isNew={isNew}
              onChange={setEditedTask}
              repeatIntervalDays={editRepeatInterval}
              repeatStartDate={editRepeatStartDate}
              onRepeatIntervalChange={setEditRepeatInterval}
              onRepeatStartDateChange={setEditRepeatStartDate}
            />
          </div>
        ) : existingTask ? (
          <div className={styles.viewSection}>
            <h1 className={styles.taskTitle}>{existingTask.title}</h1>
            {existingTask.description && (
              <p className={styles.taskDescription}>
                {existingTask.description}
              </p>
            )}
            <div className={styles.chips}>
              <span
                className={`${styles.chip} ${
                  existingTask.status === 'PENDING'
                    ? styles.statusChipPending
                    : styles.statusChip
                }`}
              >
                {existingTask.status === 'PENDING' ? 'Pending' : 'Closed'}
              </span>
              <span className={styles.chip}>
                <PriorityBadge priority={existingTask.priority} />
                Priority {existingTask.priority}
              </span>
              {existingTask.dueDate != null && (
                <span
                  className={`${styles.chip} ${
                    isOverdue(existingTask.dueDate) && existingTask.status === 'PENDING'
                      ? styles.dueDateChipOverdue
                      : styles.dueDateChip
                  }`}
                >
                  {formatDate(existingTask.dueDate)}
                </span>
              )}
            </div>
            {existingTask.aiEnabled && (
              <>
                <span className={`${styles.chip} ${styles.statusChipPending}`}>
                  AI: {(existingTask.props?.algorithm as string) === 'sdlc' ? 'SDLC' : (existingTask.props?.algorithm as string)?.includes('decompose_and_delegate') ? 'D&D' : 'Simple'}
                </span>
                {existingTask.props?.aiStatus && (
                  <span className={styles.chip}>
                    {String(existingTask.props.aiStatus).replace(/_/g, ' ')}
                  </span>
                )}
              </>
            )}
            {typeof existingTask.props?.workspace_path === 'string' && existingTask.props.workspace_path && (
              <WorkspaceChip path={existingTask.props.workspace_path as string} />
            )}
            {existingTask.taskDate != null && (
              <div className={styles.chips}>
                <span className={styles.chip}>
                  Task date: {formatDate(existingTask.taskDate)}
                </span>
              </div>
            )}
            {(existingTask.plannedTime != null || existingTask.duration != null) && (
              <div className={styles.chips}>
                {existingTask.plannedTime != null && (
                  <span className={styles.chip}>
                    Planned: {formatDateTime(existingTask.plannedTime)}
                  </span>
                )}
                {existingTask.duration != null && (
                  <span className={styles.chip}>
                    Duration: {existingTask.duration}h
                  </span>
                )}
              </div>
            )}
            {existingRepeat && (
              <div className={styles.chips}>
                <span className={styles.chip}>
                  Repeats every {existingRepeat.intervalDays} day{existingRepeat.intervalDays !== 1 ? 's' : ''} · starts {formatDate(existingRepeat.startDate)}
                </span>
              </div>
            )}
          </div>
        ) : null}

        {/* Sub-tasks section */}
        {!isNew && existingTask && (
          <div className={styles.subtasksSection}>
            <div className={styles.subtasksHeader}>
              <span className={styles.subtasksTitle}>
                Sub-tasks ({openChildren.length} open)
              </span>
              {existingTask.status === 'PENDING' && (
                <button
                  className={styles.addChildButton}
                  onClick={() =>
                    navigate(`/tasks/new?parentId=${existingTask.id}`)
                  }
                >
                  + Add Child
                </button>
              )}
            </div>
            <div className={styles.subtaskList}>
              {openChildren.map((child) => (
                <TaskItem key={child.id} task={child} showDescription />
              ))}
            </div>
            {closedChildren.length > 0 && (
              <details className={styles.closedSubtasksSection}>
                <summary className={styles.closedSubtasksTitle}>
                  Completed ({closedChildren.length})
                </summary>
                <div className={styles.subtaskList}>
                  {closedChildren.map((child) => (
                    <TaskItem key={child.id} task={child} showDescription />
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {/* Comments section */}
        {!isNew && existingTask && (
          <CommentSection taskId={existingTask.id} />
        )}
      </div>
    </div>
  );
}
