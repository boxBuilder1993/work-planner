export interface TaskEntity {
  id: string;
  parentId: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  priority: number;
  dueDate: number | null;
  createdAt: number;
  updatedAt: number;
}

export interface CommentEntity {
  id: string;
  taskId: string;
  text: string;
  createdAt: number;
  updatedAt: number;
}

export type TaskStatus = 'PENDING' | 'CLOSED';

export type StatusFilter = 'ALL' | 'PENDING' | 'CLOSED';

export type DueDateFilter = 'ANY' | 'HAS_DUE_DATE' | 'OVERDUE' | 'NO_DUE_DATE';

export type Tab = 'THEMES' | 'ACTIONABLE' | 'SEARCH';

export interface SearchFilters {
  status: StatusFilter;
  minPriority: number;
  maxPriority: number;
  dueDate: DueDateFilter;
}

export const DEFAULT_SEARCH_FILTERS: SearchFilters = {
  status: 'ALL',
  minPriority: 1,
  maxPriority: 5,
  dueDate: 'ANY',
};

export const PRIORITY_COLORS: Record<number, string> = {
  1: '#E53935',
  2: '#F57C00',
  3: '#FDD835',
  4: '#43A047',
  5: '#1E88E5',
};

export const DRIVE_FILE_TASKS = 'workplanner_tasks.enc';
export const DRIVE_FILE_COMMENTS = 'workplanner_comments.enc';
export const DRIVE_FILE_SALT = 'workplanner_salt.bin';
