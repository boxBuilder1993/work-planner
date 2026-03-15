import type { RepeatingTaskEntity } from '../types';
import { apiFetch, apiPut, apiDelete } from './client';

export function getRecurringRule(taskId: string): Promise<RepeatingTaskEntity | null> {
  return apiFetch<RepeatingTaskEntity>(`/api/tasks/${taskId}/recurring`).catch((err) => {
    if (err.status === 404) return null;
    throw err;
  });
}

export function upsertRecurringRule(taskId: string, body: {
  repetitionType: string;
  repetitionProps: Record<string, unknown>;
  startDate: number;
}): Promise<RepeatingTaskEntity> {
  return apiPut(`/api/tasks/${taskId}/recurring`, body);
}

export function deleteRecurringRule(taskId: string): Promise<void> {
  return apiDelete(`/api/tasks/${taskId}/recurring`);
}
