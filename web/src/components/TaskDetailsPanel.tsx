import { useState, useEffect, useCallback } from 'react';
import { getTask, updateTask } from '../api/tasks';
import { listComments, createComment, deleteComment } from '../api/comments';
import type { TaskEntity, CommentEntity } from '../types';
import { Textarea } from '@/components/ui/textarea';
import Markdown from './Markdown';
import { Trash2 } from 'lucide-react';

function fmtWhen(ms: number): string {
  return new Date(ms).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

const sectionTitle = 'text-[13px] font-semibold uppercase tracking-wide text-muted-foreground';

/** A task's description: rendered as markdown, click to edit inline. */
export function DescriptionSection({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<TaskEntity | null>(null);
  const [desc, setDesc] = useState('');
  const [editing, setEditing] = useState(false);

  const load = useCallback(async () => {
    const t = await getTask(taskId);
    setTask(t);
    setDesc(t.description ?? '');
  }, [taskId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount / taskId change
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    setEditing(false);
    if (!task || desc === (task.description ?? '')) return;
    setTask(await updateTask(taskId, { description: desc }));
  };
  const cancel = () => { setDesc(task?.description ?? ''); setEditing(false); };

  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h2 className={sectionTitle}>Description</h2>
        <a
          href="https://www.markdownguide.org/basic-syntax/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11.5px] font-normal text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
          title="Markdown formatting reference (opens in a new tab)"
        >
          Markdown supported ↗
        </a>
      </div>
      {editing ? (
        <Textarea
          autoFocus
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => { if (e.key === 'Escape') cancel(); }}
          placeholder="Add a description — markdown supported…  (Esc to cancel)"
          className="min-h-[110px] resize-y text-[14px] leading-relaxed"
        />
      ) : desc.trim() ? (
        <div
          role="button"
          tabIndex={0}
          onClick={() => setEditing(true)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); setEditing(true); } }}
          title="Click to edit"
          className="-mx-3 cursor-text rounded-lg border border-transparent px-3 py-2 text-[14px] leading-relaxed transition-colors hover:border-border"
        >
          <Markdown>{desc}</Markdown>
        </div>
      ) : (
        <button
          onClick={() => setEditing(true)}
          className="w-full rounded-lg border border-dashed px-3 py-3 text-left text-[13px] text-muted-foreground transition-colors hover:border-border hover:text-foreground"
        >
          Add a description — markdown supported…
        </button>
      )}
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
