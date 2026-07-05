import { useState, useEffect, useCallback } from 'react';
import { listChildren } from '../api/tasks';
import type { TaskEntity } from '../types';
import PlanTree from './PlanTree';
import { DescriptionSection, CommentsSection } from './TaskDetailsPanel';
import { cn } from '@/lib/utils';
import { ChevronRight } from 'lucide-react';

/**
 * The merged "Plan" tab for a task: its own description, then its sub-task tree
 * (collapsible — "close the work-tree"), then its comment thread. Schedule stays
 * a separate tab.
 */
export default function TaskPlan({ taskId }: { taskId: string }) {
  return (
    <div className="max-w-4xl space-y-9">
      <DescriptionSection taskId={taskId} />
      <SubtasksSection taskId={taskId} />
      <CommentsSection taskId={taskId} />
    </div>
  );
}

function SubtasksSection({ taskId }: { taskId: string }) {
  const key = `wp-subtree-open-${taskId}`;
  const [children, setChildren] = useState<TaskEntity[] | null>(null);
  const [open, setOpen] = useState<boolean | null>(null); // null until leaf status known

  const load = useCallback(async () => { setChildren(await listChildren(taskId)); }, [taskId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount / taskId change
  useEffect(() => { void load(); }, [load]);

  // Default: remember the user's choice per task; otherwise auto-close leaves.
  useEffect(() => {
    if (children === null) return;
    const stored = localStorage.getItem(key);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- derive initial open state
    setOpen(stored !== null ? stored === '1' : children.length > 0);
  }, [children, key]);

  const toggle = () => setOpen((o) => {
    const n = !o;
    localStorage.setItem(key, n ? '1' : '0');
    return n;
  });

  const count = children?.length ?? 0;

  return (
    <section>
      <button onClick={toggle} className="flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground">
        <ChevronRight className={cn('size-4 transition-transform', open && 'rotate-90')} />
        <span className="text-[13px] font-semibold uppercase tracking-wide">Sub-tasks</span>
        {count > 0 && <span className="text-[13px] font-normal normal-case tracking-normal">· {count}</span>}
      </button>

      {open === false && (
        <p className="mt-2 pl-[22px] text-[13px] text-muted-foreground">
          {count > 0 ? `${count} subtask${count === 1 ? '' : 's'} — hidden` : 'No subtasks yet.'}
        </p>
      )}
      {open && <div className="mt-3"><PlanTree rootId={taskId} /></div>}
    </section>
  );
}
