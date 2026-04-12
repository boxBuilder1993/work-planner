// Shared types with web UI - mirrors ui/src/types/finance.ts
// This file is synchronized across both web and mobile platforms

export interface TaskEntity {
  id: string;
  parentId: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  priority: number;
  dueDate: number | null;
  taskDate: number | null;
  plannedTime: number | null;
  duration: number | null;
  aiEnabled: boolean;
  props: Record<string, unknown>;
  createdAt: number;
  updatedAt: number;
}

export type CommentType = 'COMMENT' | 'PROPOSAL';
export type ProposalStatus = 'PENDING' | 'APPROVED' | 'DENIED';

export interface CommentEntity {
  id: string;
  taskId: string;
  text: string;
  parentCommentId: string | null;
  commentType: CommentType;
  createdBy: string;
  proposalStatus: ProposalStatus | null;
  proposalFeedback: string | null;
  createdAt: number;
  updatedAt: number;
}

export interface RepeatingTaskEntity {
  id: string;
  taskId: string;
  intervalDays: number;
  startDate: number;
  lastCreatedAt: number | null;
  createdAt: number;
  updatedAt: number;
}

export type TaskStatus = 'PENDING' | 'CLOSED';

export type StatusFilter = 'ALL' | 'PENDING' | 'CLOSED';

export type DueDateFilter = 'ANY' | 'HAS_DUE_DATE' | 'OVERDUE' | 'NO_DUE_DATE';

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
