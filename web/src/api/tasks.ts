import type { TaskEntity } from '../types';
import { apiFetch, apiPost, apiPatch, apiDelete } from './client';

export function listRootTasks(status?: string): Promise<TaskEntity[]> {
  const params = status ? `?status=${status}` : '';
  return apiFetch(`/api/tasks${params}`);
}

export function getTask(id: string): Promise<TaskEntity> {
  return apiFetch(`/api/tasks/${id}`);
}

export function createTask(body: {
  title: string;
  description?: string;
  parentId?: string | null;
  priority?: number;
  dueDate?: number | null;
  plannedTime?: number | null;
  duration?: number | null;
}): Promise<TaskEntity> {
  return apiPost('/api/tasks', body);
}

export function updateTask(id: string, body: {
  title?: string;
  description?: string;
  status?: string;
  priority?: number;
  dueDate?: number | null;
  plannedTime?: number | null;
  duration?: number | null;
}): Promise<TaskEntity> {
  return apiPatch(`/api/tasks/${id}`, body);
}

export function deleteTask(id: string): Promise<void> {
  return apiDelete(`/api/tasks/${id}`);
}

export function listChildren(parentId: string): Promise<TaskEntity[]> {
  return apiFetch(`/api/tasks/${parentId}/children`);
}

export function getBreadcrumbs(taskId: string): Promise<TaskEntity[]> {
  return apiFetch(`/api/tasks/${taskId}/breadcrumbs`);
}

export function listExecutableTasks(): Promise<TaskEntity[]> {
  return apiFetch('/api/tasks/executable');
}

export function searchTasks(query: string): Promise<TaskEntity[]> {
  return apiFetch(`/api/tasks/search?q=${encodeURIComponent(query)}`);
}
