import { useState, useEffect, useCallback } from 'react';
import { getTask, updateTask } from '../api/tasks';
import { listComments, createComment, deleteComment } from '../api/comments';
import type { TaskEntity, CommentEntity } from '../types';
import { Textarea } from '@/components/ui/textarea';
import { Trash2 } from 'lucide-react';

function fmtWhen(ms: number): string {
  return new Date(ms).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

const sectionTitle = 'text-[13px] font-semibold uppercase tracking-wide text-muted-foreground';

/** Editable description for a task. */
export function DescriptionSection({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<TaskEntity | null>(null);
  const [desc, setDesc] = useState('');

  const load = useCallback(async () => {
    const t = await getTask(taskId);
    setTask(t);
    setDesc(t.description ?? '');
  }, [taskId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount / taskId change
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    if (!task || desc === (task.description ?? '')) return;
    setTask(await updateTask(taskId, { description: desc }));
  };

  return (
    <section>
      <h2 className={`mb-2 ${sectionTitle}`}>Description</h2>
      <Textarea
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        onBlur={save}
        placeholder="Add a description — context, scope, links…"
        className="min-h-[110px] resize-y text-[14px] leading-relaxed"
      />
    </section>
  );
}

/** A task's comment thread + composer. */
export function CommentsSection({ taskId }: { taskId: string }) {
  const [comments, setComments] = useState<CommentEntity[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => { setComments(await listComments(taskId)); }, [taskId]);
  useEffect(() => { void load(); }, [load]);

  const add = async () => {
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

  return (
    <section>
      <h2 className={`mb-3 ${sectionTitle}`}>
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
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void add(); }}
          placeholder="Write a comment…  (⌘↵ to send)"
          className="min-h-[72px] resize-y text-[14px]"
        />
        <div className="mt-2 flex justify-end">
          <button
            onClick={() => void add()}
            disabled={!draft.trim() || busy}
            className="inline-flex h-[34px] items-center rounded-md bg-primary px-3.5 text-[13px] font-medium text-primary-foreground disabled:opacity-50"
          >
            Comment
          </button>
        </div>
      </div>
    </section>
  );
}
