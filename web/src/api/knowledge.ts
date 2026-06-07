import { apiFetch, apiPost, apiPatch, apiDelete } from './client';

export interface KnowledgeCard {
  id: string;
  content: string;
  tags: string[];
  isValid: boolean;
  createdAt: number;
  updatedAt: number;
}

export interface CreateCardInput {
  id: string;
  content: string;
  tags?: string[];
}

export interface UpdateCardInput {
  content?: string;
  tags?: string[];
  isValid?: boolean;
}

export function listCards(opts?: { tag?: string; includeInvalid?: boolean }): Promise<KnowledgeCard[]> {
  const p = new URLSearchParams();
  if (opts?.tag) p.set('tag', opts.tag);
  if (opts?.includeInvalid) p.set('includeInvalid', 'true');
  const qs = p.toString();
  return apiFetch<KnowledgeCard[]>(`/api/knowledge-cards${qs ? `?${qs}` : ''}`);
}

export function searchCards(
  q: string,
  opts?: { tag?: string; includeInvalid?: boolean; limit?: number },
): Promise<KnowledgeCard[]> {
  const p = new URLSearchParams();
  if (q) p.set('q', q);
  if (opts?.tag) p.set('tag', opts.tag);
  if (opts?.includeInvalid) p.set('includeInvalid', 'true');
  if (opts?.limit) p.set('limit', String(opts.limit));
  return apiFetch<KnowledgeCard[]>(`/api/knowledge-cards/search?${p.toString()}`);
}

export function createCard(input: CreateCardInput): Promise<KnowledgeCard> {
  return apiPost<KnowledgeCard>('/api/knowledge-cards', input);
}

export function updateCard(id: string, input: UpdateCardInput): Promise<KnowledgeCard> {
  return apiPatch<KnowledgeCard>(`/api/knowledge-cards/${encodeURIComponent(id)}`, input);
}

export function deleteCard(id: string): Promise<void> {
  return apiDelete(`/api/knowledge-cards/${encodeURIComponent(id)}`);
}
