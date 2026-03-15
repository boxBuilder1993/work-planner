import type { CommentEntity, CommentType } from '../types';
import { apiFetch, apiPost, apiDelete } from './client';

export function listComments(taskId: string): Promise<CommentEntity[]> {
  return apiFetch(`/api/tasks/${taskId}/comments`);
}

export function createComment(
  taskId: string,
  text: string,
  options?: {
    parentCommentId?: string;
    commentType?: CommentType;
    createdBy?: string;
  },
): Promise<CommentEntity> {
  return apiPost(`/api/tasks/${taskId}/comments`, {
    text,
    parentCommentId: options?.parentCommentId ?? null,
    commentType: options?.commentType ?? 'COMMENT',
    createdBy: options?.createdBy ?? 'user',
  });
}

export function deleteComment(commentId: string): Promise<void> {
  return apiDelete(`/api/comments/${commentId}`);
}

export function approveProposal(commentId: string): Promise<CommentEntity> {
  return apiPost(`/api/comments/${commentId}/approve`, {});
}

export function denyProposal(commentId: string, feedback?: string): Promise<CommentEntity> {
  return apiPost(`/api/comments/${commentId}/deny`, { feedback: feedback ?? '' });
}
