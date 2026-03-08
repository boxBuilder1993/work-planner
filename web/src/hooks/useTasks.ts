import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { createElement } from 'react';
import type { TaskEntity, CommentEntity } from '../types';

interface TasksContextValue {
  // Task queries
  getPendingRootTasks: () => TaskEntity[];
  getLeafTasks: () => TaskEntity[];
  getChildTasks: (parentId: string) => TaskEntity[];
  getTaskById: (id: string) => TaskEntity | undefined;
  searchTasks: (query: string) => TaskEntity[];
  getBreadcrumbs: (taskId: string) => TaskEntity[];
  getDescendantIds: (rootId: string) => Set<string>;
  getAllTasks: () => Map<string, TaskEntity>;
  getAllComments: () => Map<string, CommentEntity>;

  // Task mutations
  createTask: (params: {
    title: string;
    description?: string;
    parentId?: string | null;
    priority?: number;
    dueDate?: number | null;
  }) => TaskEntity;
  updateTask: (task: TaskEntity) => void;
  deleteTask: (taskId: string) => void;

  // Comment operations
  getCommentsForTask: (taskId: string) => CommentEntity[];
  addComment: (taskId: string, text: string) => CommentEntity;
  deleteComment: (commentId: string) => void;

  // Initialization
  loadFromRestore: (
    tasks: Record<string, TaskEntity>,
    comments: Record<string, CommentEntity>,
  ) => void;
  clearAll: () => void;

  // Serialization for backup
  getTasksRecord: () => Record<string, TaskEntity>;
  getCommentsRecord: () => Record<string, CommentEntity>;
}

const TasksContext = createContext<TasksContextValue | null>(null);

export function useTasks(): TasksContextValue {
  const ctx = useContext(TasksContext);
  if (!ctx) throw new Error('useTasks must be used within TasksProvider');
  return ctx;
}

function generateUUID(): string {
  return crypto.randomUUID();
}

export function TasksProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Map<string, TaskEntity>>(new Map());
  const [comments, setComments] = useState<Map<string, CommentEntity>>(
    new Map(),
  );

  const getPendingRootTasks = useCallback((): TaskEntity[] => {
    const result: TaskEntity[] = [];
    for (const task of tasks.values()) {
      if (task.parentId === null && task.status === 'PENDING') {
        result.push(task);
      }
    }
    return result.sort((a, b) => a.createdAt - b.createdAt);
  }, [tasks]);

  const getLeafTasks = useCallback((): TaskEntity[] => {
    // A leaf task is a pending task that has no children
    const parentIds = new Set<string>();
    for (const task of tasks.values()) {
      if (task.parentId) parentIds.add(task.parentId);
    }
    const result: TaskEntity[] = [];
    for (const task of tasks.values()) {
      if (task.status === 'PENDING' && !parentIds.has(task.id)) {
        result.push(task);
      }
    }
    return result.sort((a, b) => a.createdAt - b.createdAt);
  }, [tasks]);

  const getChildTasks = useCallback(
    (parentId: string): TaskEntity[] => {
      const result: TaskEntity[] = [];
      for (const task of tasks.values()) {
        if (task.parentId === parentId) {
          result.push(task);
        }
      }
      return result.sort((a, b) => a.createdAt - b.createdAt);
    },
    [tasks],
  );

  const getTaskById = useCallback(
    (id: string): TaskEntity | undefined => {
      return tasks.get(id);
    },
    [tasks],
  );

  const searchTasks = useCallback(
    (query: string): TaskEntity[] => {
      if (!query.trim()) return [];
      const lower = query.toLowerCase();
      const result: TaskEntity[] = [];
      for (const task of tasks.values()) {
        if (
          task.title.toLowerCase().includes(lower) ||
          task.description.toLowerCase().includes(lower)
        ) {
          result.push(task);
        }
      }
      return result.sort((a, b) => a.createdAt - b.createdAt);
    },
    [tasks],
  );

  const getBreadcrumbs = useCallback(
    (taskId: string): TaskEntity[] => {
      const crumbs: TaskEntity[] = [];
      let current = tasks.get(taskId);
      while (current) {
        crumbs.unshift(current);
        current = current.parentId ? tasks.get(current.parentId) : undefined;
      }
      return crumbs;
    },
    [tasks],
  );

  const getDescendantIds = useCallback(
    (rootId: string): Set<string> => {
      const descendants = new Set<string>();
      const stack = [rootId];
      while (stack.length > 0) {
        const currentId = stack.pop()!;
        for (const task of tasks.values()) {
          if (task.parentId === currentId && !descendants.has(task.id)) {
            descendants.add(task.id);
            stack.push(task.id);
          }
        }
      }
      return descendants;
    },
    [tasks],
  );

  const getAllTasks = useCallback(() => tasks, [tasks]);
  const getAllComments = useCallback(() => comments, [comments]);

  const createTask = useCallback(
    (params: {
      title: string;
      description?: string;
      parentId?: string | null;
      priority?: number;
      dueDate?: number | null;
    }): TaskEntity => {
      const now = Date.now();
      const task: TaskEntity = {
        id: generateUUID(),
        parentId: params.parentId ?? null,
        title: params.title,
        description: params.description ?? '',
        status: 'PENDING',
        priority: params.priority ?? 3,
        dueDate: params.dueDate ?? null,
        createdAt: now,
        updatedAt: now,
      };
      setTasks((prev) => {
        const next = new Map(prev);
        next.set(task.id, task);
        return next;
      });
      return task;
    },
    [],
  );

  const updateTask = useCallback((task: TaskEntity) => {
    const updated = { ...task, updatedAt: Date.now() };
    setTasks((prev) => {
      const next = new Map(prev);
      next.set(updated.id, updated);
      return next;
    });
  }, []);

  const deleteTask = useCallback(
    (taskId: string) => {
      // CASCADE: collect all descendant IDs
      const toDelete = new Set<string>([taskId]);
      const stack = [taskId];
      // We need to read current tasks from state at call time
      setTasks((prev) => {
        const next = new Map(prev);
        // Collect descendants
        while (stack.length > 0) {
          const currentId = stack.pop()!;
          for (const [id, task] of next) {
            if (task.parentId === currentId && !toDelete.has(id)) {
              toDelete.add(id);
              stack.push(id);
            }
          }
        }
        for (const id of toDelete) {
          next.delete(id);
        }
        return next;
      });

      // Delete comments for all deleted tasks
      setComments((prev) => {
        const next = new Map(prev);
        for (const [id, comment] of next) {
          if (toDelete.has(comment.taskId)) {
            next.delete(id);
          }
        }
        return next;
      });
    },
    [],
  );

  const getCommentsForTask = useCallback(
    (taskId: string): CommentEntity[] => {
      const result: CommentEntity[] = [];
      for (const comment of comments.values()) {
        if (comment.taskId === taskId) {
          result.push(comment);
        }
      }
      return result.sort((a, b) => a.createdAt - b.createdAt);
    },
    [comments],
  );

  const addComment = useCallback(
    (taskId: string, text: string): CommentEntity => {
      const now = Date.now();
      const comment: CommentEntity = {
        id: generateUUID(),
        taskId,
        text,
        createdAt: now,
        updatedAt: now,
      };
      setComments((prev) => {
        const next = new Map(prev);
        next.set(comment.id, comment);
        return next;
      });
      return comment;
    },
    [],
  );

  const deleteComment = useCallback((commentId: string) => {
    setComments((prev) => {
      const next = new Map(prev);
      next.delete(commentId);
      return next;
    });
  }, []);

  const loadFromRestore = useCallback(
    (
      restoredTasks: Record<string, TaskEntity>,
      restoredComments: Record<string, CommentEntity>,
    ) => {
      const taskMap = new Map(Object.entries(restoredTasks));
      const commentMap = new Map(Object.entries(restoredComments));
      setTasks(taskMap);
      setComments(commentMap);
    },
    [],
  );

  const clearAll = useCallback(() => {
    setTasks(new Map());
    setComments(new Map());
  }, []);

  const getTasksRecord = useCallback((): Record<string, TaskEntity> => {
    return Object.fromEntries(tasks);
  }, [tasks]);

  const getCommentsRecord = useCallback((): Record<string, CommentEntity> => {
    return Object.fromEntries(comments);
  }, [comments]);

  const value: TasksContextValue = {
    getPendingRootTasks,
    getLeafTasks,
    getChildTasks,
    getTaskById,
    searchTasks,
    getBreadcrumbs,
    getDescendantIds,
    getAllTasks,
    getAllComments,
    createTask,
    updateTask,
    deleteTask,
    getCommentsForTask,
    addComment,
    deleteComment,
    loadFromRestore,
    clearAll,
    getTasksRecord,
    getCommentsRecord,
  };

  return createElement(TasksContext.Provider, { value }, children);
}
