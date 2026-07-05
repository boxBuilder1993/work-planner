import { useState, useEffect, useCallback } from 'react';
import * as planner from '../api/planner';
import type { ScheduleRow, Person, Dependency } from '../api/planner';
import { updateTask } from '../api/tasks';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import StatusSelect from './StatusSelect';
import AssigneeSelect from './AssigneeSelect';
import { X } from 'lucide-react';

const inputCls = 'h-8 w-full rounded-md border bg-background px-2 text-[13px] tabular-nums outline-none focus:border-foreground';
const ctrlCls = 'h-8 w-full text-[13px]';
const toYMD = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const fromYMD = (s: string): number | null => (s ? Date.parse(s + 'T00:00:00Z') : null);

/** The task's own editable properties — a box above the description on the Plan tab. */
export default function TaskProperties({ taskId }: { taskId: string }) {
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [deps, setDeps] = useState<Dependency[]>([]);
  const [depErr, setDepErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [s, p, d] = await Promise.all([planner.getSchedule(), planner.listPeople(), planner.listDependencies(taskId)]);
    setRows(s); setPeople(p); setDeps(d); setLoading(false);
  }, [taskId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount / taskId change
  useEffect(() => { void load(); }, [load]);

  const row = rows.find((r) => r.taskId === taskId);
  const isLeaf = !rows.some((r) => r.parentId === taskId);
  const byId = new Map(rows.map((r) => [r.taskId, r]));

  if (loading || !row) return <div className="rounded-xl border p-4 text-sm text-muted-foreground">Loading…</div>;

  const setAssignee = (v: string) => planner.updateTaskPlanner(taskId, { assigneeId: v }).then(load);
  const setStatus = (v: string) => updateTask(taskId, { status: v }).then(load);
  const setDue = (v: string) => updateTask(taskId, { dueDate: fromYMD(v) }).then(load);
  const setEstimate = (v: string) => updateTask(taskId, { duration: v === '' ? null : Number(v) }).then(load);
  const setPriority = (v: string) => planner.updateTaskPlanner(taskId, { plannerPriority: v === '' ? 0 : Number(v) }).then(load);
  const setBuffer = (v: string) => planner.updateTaskPlanner(taskId, { bufferHours: v === '' ? 0 : Number(v) }).then(load);
  const addDep = async (blockerId: string) => {
    if (!blockerId) return;
    try { await planner.createDependency(taskId, blockerId); setDepErr(null); await load(); }
    catch { setDepErr('Could not add — that would create a cycle.'); }
  };
  const removeDep = (id: string) => planner.deleteDependency(id).then(load);

  const candidates = rows.filter((r) => r.taskId !== taskId && !deps.some((d) => d.dependsOnId === r.taskId));

  return (
    <div className="rounded-xl border p-4">
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
        <Field label="Status"><StatusSelect value={row.status} onChange={setStatus} className={ctrlCls} /></Field>
        <Field label="Assignee"><AssigneeSelect value={row.assigneeId ?? ''} people={people} onChange={setAssignee} className={ctrlCls} /></Field>
        <Field label="Due date">
          <input type="date" value={row.dueDate ? toYMD(row.dueDate) : ''} onChange={(e) => setDue(e.target.value)} className={inputCls} />
        </Field>
        <Field label={isLeaf ? 'Estimate (h)' : 'Estimate (rolled up)'}>
          {isLeaf ? (
            <input type="number" min="0" step="0.5" defaultValue={row.estimateHours ?? ''} onBlur={(e) => setEstimate(e.target.value)} className={inputCls} placeholder="—" />
          ) : (
            <div className="flex h-8 items-center text-[13px] tabular-nums text-muted-foreground">{row.estimateHours ?? '—'}h</div>
          )}
        </Field>
        <Field label="Priority"><input type="number" step="0.1" defaultValue={row.priority || ''} onBlur={(e) => setPriority(e.target.value)} className={inputCls} placeholder="—" title="Lower = higher priority; blank = unset" /></Field>
        {!isLeaf && <Field label="Buffer (h)"><input type="number" min="0" defaultValue={row.bufferHours ?? ''} onBlur={(e) => setBuffer(e.target.value)} className={inputCls} placeholder="0" /></Field>}
      </div>

      <div className="mt-4 border-t pt-3">
        <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Blocked by</div>
        <div className="flex flex-wrap items-center gap-1.5">
          {deps.length === 0 && <span className="text-[13px] text-muted-foreground">Nothing — this can start anytime.</span>}
          {deps.map((d) => (
            <span key={d.id} className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[12px]">
              {byId.get(d.dependsOnId)?.title ?? 'task'}
              <button onClick={() => removeDep(d.id)} className="text-muted-foreground hover:text-destructive" title="Remove"><X className="size-3" /></button>
            </span>
          ))}
          <div className="w-[190px]">
            <Select value="" onValueChange={addDep}>
              <SelectTrigger className="h-7 text-[12px]"><SelectValue placeholder="+ add blocker…" /></SelectTrigger>
              <SelectContent>
                {candidates.length === 0 && <div className="px-2 py-1.5 text-[12px] text-muted-foreground">No other tasks</div>}
                {candidates.map((r) => <SelectItem key={r.taskId} value={r.taskId}>{r.title}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        {depErr && <p className="mt-1.5 text-[12px] text-destructive">{depErr}</p>}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      {children}
    </div>
  );
}
