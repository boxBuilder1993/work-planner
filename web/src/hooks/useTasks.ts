import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import { createElement } from 'react';
import type { TaskEntity, CommentEntity, CommentType, RepeatingTaskEntity } from '../types';
import * as tasksApi from '../api/tasks';
import * as commentsApi from '../api/comments';
import * as recurringApi from '../api/recurring';

interface TasksContextValue {
  // Task queries
  getPendingRootTasks: () => TaskEntity[];
  getLeafTasks: () => TaskEntity[];
  getChildTasks: (parentId: string) => TaskEntity[];
  getTaskById: (id: string) => TaskEntity | undefined;
  searchTasks: (query: string) => Promise<TaskEntity[]>;
  getBreadcrumbs: (taskId: string) => Promise<TaskEntity[]>;
  getDescendantIds: (rootId: string) => Set<string>;
  getAllTasks: () => Map<string, TaskEntity>;
  getAllComments: () => Map<string, CommentEntity>;

  // Repeating tasks
  getRepeatingTaskForTask: (taskId: string) => RepeatingTaskEntity | undefined;
  setRepeatingTask: (taskId: string, intervalDays: number, startDate: number) => Promise<void>;
  removeRepeatingTask: (taskId: string) => Promise<void>;
  fetchRepeatingTask: (taskId: string) => Promise<RepeatingTaskEntity | null>;

  // Task mutations
  createTask: (params: {
    title: string;
    description?: string;
    parentId?: string | null;
    priority?: number;
    dueDate?: number | null;
    plannedTime?: number | null;
    duration?: number | null;
  }) => Promise<TaskEntity>;
  updateTask: (task: TaskEntity) => Promise<void>;
  deleteTask: (taskId: string) => Promise<void>;

  // Comment operations
  getCommentsForTask: (taskId: string) => CommentEntity[];
  fetchCommentsForTask: (taskId: string) => Promise<CommentEntity[]>;
  addComment: (
    taskId: string,
    text: string,
    options?: { parentCommentId?: string; commentType?: CommentType; createdBy?: string },
  ) => Promise<CommentEntity>;
  deleteComment: (commentId: string) => Promise<void>;
  approveProposal: (commentId: string) => Promise<void>;
  denyProposal: (commentId: string, feedback?: string) => Promise<void>;

  // Fetch helpers
  refreshTask: (taskId: string) => Promise<void>;
  refreshRootTasks: () => Promise<void>;
  refreshChildren: (parentId: string) => Promise<void>;
  refreshLeafTasks: () => Promise<void>;

  // Initialization
  clearAll: () => void;
}

const TasksContext = createContext<TasksContextValue | null>(null);

export function useTasks(): TasksContextValue {
  const ctx = useContext(TasksContext);
  if (!ctx) throw new Error('useTasks must be used within TasksProvider');
  return ctx;
}

export function TasksProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<Map<string, TaskEntity>>(new Map());
  const [comments, setComments] = useState<Map<string, CommentEntity>>(new Map());
  const [repeatingTasks, setRepeatingTasks] = useState<Map<string, RepeatingTaskEntity>>(new Map());
  const [leafTasks, setLeafTasks] = useState<TaskEntity[]>([]);

  // Fetch root tasks on mount.
  useEffect(() => {
    tasksApi.listRootTasks('PENDING').then((rootTasks) => {
      setTasks((prev) => {
        const next = new Map(prev);
        for (const t of rootTasks) next.set(t.id, t);
        return next;
      });
    }).catch(() => {});

    tasksApi.listExecutableTasks().then(setLeafTasks).catch(() => {});
  }, []);

  const refreshTask = useCallback(async (taskId: string) => {
    const t = await tasksApi.getTask(taskId);
    setTasks((prev) => new Map(prev).set(t.id, t));
  }, []);

  const refreshRootTasks = useCallback(async () => {
    const rootTasks = await tasksApi.listRootTasks('PENDING');
    setTasks((prev) => {
      const next = new Map(prev);
      for (const t of rootTasks) next.set(t.id, t);
      return next;
    });
  }, []);

  const refreshChildren = useCallback(async (parentId: string) => {
    const ch = await tasksApi.listChildren(parentId);
    setTasks((prev) => {
      const next = new Map(prev);
      for (const t of ch) next.set(t.id, t);
      return next;
    });
  }, []);

  const refreshLeafTasks = useCallback(async () => {
    const leaves = await tasksApi.listExecutableTasks();
    setLeafTasks(leaves);
  }, []);

  const getPendingRootTasks = useCallback((): TaskEntity[] => {
    const result: TaskEntity[] = [];
    for (const task of tasks.values()) {
      if (task.parentId === null && task.status === 'PENDING') {
        result.push(task);
      }
    }
    return result.sort((a, b) => a.createdAt - b.createdAt);
  }, [tasks]);

  const getLeafTasks = useCallback((): TaskEntity[] => leafTasks, [leafTasks]);

  const getChildTasks = useCallback(
    (parentId: string): TaskEntity[] => {
      const result: TaskEntity[] = [];
      for (const task of tasks.values()) {
        if (task.parentId === parentId) result.push(task);
      }
      return result.sort((a, b) => a.createdAt - b.createdAt);
    },
    [tasks],
  );

  const getTaskById = useCallback(
    (id: string): TaskEntity | undefined => tasks.get(id),
    [tasks],
  );

  const searchTasksFn = useCallback(async (query: string): Promise<TaskEntity[]> => {
    if (!query.trim()) return [];
    const results = await tasksApi.searchTasks(query);
    setTasks((prev) => {
      const next = new Map(prev);
      for (const t of results) next.set(t.id, t);
      return next;
    });
    return results;
  }, []);

  const getBreadcrumbsFn = useCallback(async (taskId: string): Promise<TaskEntity[]> => {
    const crumbs = await tasksApi.getBreadcrumbs(taskId);
    setTasks((prev) => {
      const next = new Map(prev);
      for (const t of crumbs) next.set(t.id, t);
      return next;
    });
    return crumbs;
  }, []);

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
    async (params: {
      title: string;
      description?: string;
      parentId?: string | null;
      priority?: number;
      dueDate?: number | null;
      plannedTime?: number | null;
      duration?: number | null;
    }): Promise<TaskEntity> => {
      const task = await tasksApi.createTask(params);
      setTasks((prev) => {
        const next = new Map(prev);
        next.set(task.id, task);
        return next;
      });
      refreshLeafTasks();
      return task;
    },
    [refreshLeafTasks],
  );

  const updateTask = useCallback(async (task: TaskEntity) => {
    const updated = await tasksApi.updateTask(task.id, {
      title: task.title,
      description: task.description,
      status: task.status,
      priority: task.priority,
      dueDate: task.dueDate,
      plannedTime: task.plannedTime,
      duration: task.duration,
      aiEnabled: task.aiEnabled,
    });
    setTasks((prev) => {
      const next = new Map(prev);
      next.set(updated.id, updated);
      return next;
    });
    refreshLeafTasks();
  }, [refreshLeafTasks]);

  const deleteTask = useCallback(
    async (taskId: string) => {
      await tasksApi.deleteTask(taskId);
      const toDelete = new Set<string>([taskId]);
      setTasks((prev) => {
        const next = new Map(prev);
        const stack = [taskId];
        while (stack.length > 0) {
          const currentId = stack.pop()!;
          for (const [id, t] of next) {
            if (t.parentId === currentId && !toDelete.has(id)) {
              toDelete.add(id);
              stack.push(id);
            }
          }
        }
        for (const id of toDelete) next.delete(id);
        return next;
      });
      setComments((prev) => {
        const next = new Map(prev);
        for (const [id, c] of next) {
          if (toDelete.has(c.taskId)) next.delete(id);
        }
        return next;
      });
      refreshLeafTasks();
    },
    [refreshLeafTasks],
  );

  const getCommentsForTask = useCallback(
    (taskId: string): CommentEntity[] => {
      const result: CommentEntity[] = [];
      for (const comment of comments.values()) {
        if (comment.taskId === taskId) result.push(comment);
      }
      return result.sort((a, b) => a.createdAt - b.createdAt);
    },
    [comments],
  );

  const fetchCommentsForTask = useCallback(async (taskId: string): Promise<CommentEntity[]> => {
    const list = await commentsApi.listComments(taskId);
    setComments((prev) => {
      const next = new Map(prev);
      for (const [id, c] of next) {
        if (c.taskId === taskId) next.delete(id);
      }
      for (const c of list) next.set(c.id, c);
      return next;
    });
    return list;
  }, []);

  const addComment = useCallback(
    async (
      taskId: string,
      text: string,
      options?: { parentCommentId?: string; commentType?: CommentType; createdBy?: string },
    ): Promise<CommentEntity> => {
      const comment = await commentsApi.createComment(taskId, text, options);
      setComments((prev) => {
        const next = new Map(prev);
        next.set(comment.id, comment);
        return next;
      });
      return comment;
    },
    [],
  );

  const approveProposal = useCallback(async (commentId: string) => {
    const updated = await commentsApi.approveProposal(commentId);
    setComments((prev) => {
      const next = new Map(prev);
      next.set(updated.id, updated);
      return next;
    });
  }, []);

  const denyProposal = useCallback(async (commentId: string, feedback?: string) => {
    const updated = await commentsApi.denyProposal(commentId, feedback);
    setComments((prev) => {
      const next = new Map(prev);
      next.set(updated.id, updated);
      return next;
    });
  }, []);

  const deleteComment = useCallback(async (commentId: string) => {
    await commentsApi.deleteComment(commentId);
    setComments((prev) => {
      const next = new Map(prev);
      next.delete(commentId);
      return next;
    });
  }, []);

  const getRepeatingTaskForTask = useCallback(
    (taskId: string): RepeatingTaskEntity | undefined => {
      for (const rt of repeatingTasks.values()) {
        if (rt.taskId === taskId) return rt;
      }
      return undefined;
    },
    [repeatingTasks],
  );

  const fetchRepeatingTask = useCallback(async (taskId: string): Promise<RepeatingTaskEntity | null> => {
    const rt = await recurringApi.getRecurringRule(taskId);
    if (rt) {
      setRepeatingTasks((prev) => {
        const next = new Map(prev);
        next.set(rt.id, rt);
        return next;
      });
    }
    return rt;
  }, []);

  const setRepeatingTask = useCallback(
    async (taskId: string, intervalDays: number, startDate: number) => {
      const rt = await recurringApi.upsertRecurringRule(taskId, {
        repetitionType: 'interval_days',
        repetitionProps: { interval_days: intervalDays },
        startDate,
      });
      setRepeatingTasks((prev) => {
        const next = new Map(prev);
        next.set(rt.id, rt);
        return next;
      });
    },
    [],
  );

  const removeRepeatingTask = useCallback(async (taskId: string) => {
    await recurringApi.deleteRecurringRule(taskId);
    setRepeatingTasks((prev) => {
      const next = new Map(prev);
      for (const [id, rt] of next) {
        if (rt.taskId === taskId) {
          next.delete(id);
          break;
        }
      }
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setTasks(new Map());
    setComments(new Map());
    setRepeatingTasks(new Map());
    setLeafTasks([]);
  }, []);

  const value: TasksContextValue = {
    getPendingRootTasks,
    getLeafTasks,
    getChildTasks,
    getTaskById,
    searchTasks: searchTasksFn,
    getBreadcrumbs: getBreadcrumbsFn,
    getDescendantIds,
    getAllTasks,
    getAllComments,
    createTask,
    updateTask,
    deleteTask,
    getCommentsForTask,
    fetchCommentsForTask,
    addComment,
    deleteComment,
    approveProposal,
    denyProposal,
    getRepeatingTaskForTask,
    setRepeatingTask,
    removeRepeatingTask,
    fetchRepeatingTask,
    refreshTask,
    refreshRootTasks,
    refreshChildren,
    refreshLeafTasks,
    clearAll,
  };

  return createElement(TasksContext.Provider, { value }, children);
}
