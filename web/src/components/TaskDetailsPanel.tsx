import { useState, useEffect, useCallback } from 'react';
import { getTask, updateTask } from '../api/tasks';
import { listComments, createComment, deleteComment } from '../api/comments';
import type { TaskEntity, CommentEntity } from '../types';
import { Textarea } from '@/components/ui/textarea';
import { Trash2 } from 'lucide-react';

function fmtWhen(ms: number): string {
  return new Date(ms).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

/** A task's own description + comment thread — the "Details" tab of a project/task. */
export default function TaskDetailsPanel({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<TaskEntity | null>(null);
  const [desc, setDesc] = useState('');
  const [comments, setComments] = useState<CommentEntity[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [t, c] = await Promise.all([getTask(taskId), listComments(taskId)]);
    setTask(t);
    setDesc(t.description ?? '');
    setComments(c);
  }, [taskId]);
  useEffect(() => { void load(); }, [load]);

  const saveDesc = async () => {
    if (!task || desc === (task.description ?? '')) return;
    const updated = await updateTask(taskId, { description: desc });
    setTask(updated);
  };

  const addComment = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await createComment(taskId, text);
      setDraft('');
      setComments(await listComments(taskId));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    await deleteComment(id);
    setComments((cs) => cs.filter((c) => c.id !== id));
  };

  if (!task) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-3xl space-y-8">
      <section>
        <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">Description</h2>
        <Textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          onBlur={saveDesc}
          placeholder="Add a description — context, scope, links…"
          className="min-h-[120px] resize-y text-[14px] leading-relaxed"
        />
      </section>

      <section>
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">
          Comments{comments.length > 0 && <span className="ml-1.5 font-normal normal-case tracking-normal text-muted-foreground">· {comments.length}</span>}
        </h2>

        <div className="space-y-3">
          {comments.length === 0 && <p className="text-sm text-muted-foreground">No comments yet.</p>}
          {comments.map((c) => (
            <div key={c.id} className="group rounded-lg border px-3.5 py-2.5">
              <div className="mb-1 flex items-center gap-2 text-[11.5px] text-muted-foreground">
                <span className="font-medium text-foreground">{c.createdBy || 'You'}</span>
                <span>·</span>
                <span>{fmtWhen(c.createdAt)}</span>
                {c.commentType === 'PROPOSAL' && (
                  <span className="rounded-full border px-1.5 py-px text-[10px] font-medium uppercase">proposal{c.proposalStatus ? ` · ${c.proposalStatus.toLowerCase()}` : ''}</span>
                )}
                <button
                  onClick={() => void remove(c.id)}
                  className="ml-auto opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                  title="Delete comment"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
              <p className="whitespace-pre-wrap text-[14px] leading-relaxed">{c.text}</p>
            </div>
          ))}
        </div>

        <div className="mt-4">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void addComment(); }}
            placeholder="Write a comment…  (⌘↵ to send)"
            className="min-h-[72px] resize-y text-[14px]"
          />
          <div className="mt-2 flex justify-end">
            <button
              onClick={() => void addComment()}
              disabled={!draft.trim() || busy}
              className="inline-flex h-[34px] items-center rounded-md bg-primary px-3.5 text-[13px] font-medium text-primary-foreground disabled:opacity-50"
            >
              Comment
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
