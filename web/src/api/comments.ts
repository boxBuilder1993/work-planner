import type { CommentEntity } from '../types';
import { apiFetch, apiPost, apiDelete } from './client';

export function listComments(taskId: string): Promise<CommentEntity[]> {
  return apiFetch(`/api/tasks/${taskId}/comments`);
}

export function createComment(taskId: string, text: string): Promise<CommentEntity> {
  return apiPost(`/api/tasks/${taskId}/comments`, { text });
}

export function deleteComment(commentId: string): Promise<void> {
  return apiDelete(`/api/comments/${commentId}`);
}
