import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { createTask, updateTask } from '../api/tasks';
import * as planner from '../api/planner';
import type { Person, ScheduleRow } from '../api/planner';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import styles from './Planner.module.css';

// Radix Select forbids an empty-string item value, so "unassigned" uses a sentinel.
const UNASSIGNED = '__unassigned__';
const triggerCls = 'h-7 w-full min-w-[112px] px-2 text-[13px]';

function AssigneeSelect({ value, people, onChange }: { value: string; people: Person[]; onChange: (v: string) => void }) {
  return (
    <Select value={value || UNASSIGNED} onValueChange={(v) => onChange(v === UNASSIGNED ? '' : v)}>
      <SelectTrigger className={triggerCls}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={UNASSIGNED}>— unassigned —</SelectItem>
        {people.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

function StatusSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={triggerCls}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value="PENDING">To do</SelectItem>
        <SelectItem value="IN_PROGRESS">In progress</SelectItem>
        <SelectItem value="CLOSED">Done</SelectItem>
      </SelectContent>
    </Select>
  );
}

/**
 * Editable WBS tree-table. A "project" is just a task, so the same tree renders
 * the whole workspace (rootId undefined → forest of root tasks) or a single
 * task's subtree (rootId set → that task's descendants, e.g. on the task page).
 */
export default function PlanTree({ rootId }: { rootId?: string }) {
  const navigate = useNavigate();
  const collapseKey = `wp-planner-collapsed-${rootId ?? 'root'}`;

  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState<Set<string>>(
    () => new Set<string>(JSON.parse(localStorage.getItem(`wp-planner-collapsed-${rootId ?? 'root'}`) || '[]')),
  );
  const [depsFor, setDepsFor] = useState<string | null>(null);
  const [deps, setDeps] = useState<planner.Dependency[]>([]);
  const [depErr, setDepErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ parentId: string | null; title: string; estimate: string; assigneeId: string } | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const [dropTarget, setDropTarget] = useState<{ id: string; mode: 'before' | 'after' | 'into' } | null>(null);

  const reload = useCallback(async () => {
    const [s, p] = await Promise.all([planner.getSchedule(), planner.listPeople()]);
    setRows(s);
    setPeople(p);
    setLoading(false);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => { localStorage.setItem(collapseKey, JSON.stringify([...collapsed])); }, [collapsed, collapseKey]);

  const byParent = new Map<string | null, ScheduleRow[]>();
  for (const r of rows) {
    const k = r.parentId;
    if (!byParent.has(k)) byParent.set(k, []);
    byParent.get(k)!.push(r);
  }
  // Order siblings by manual position (drag order) — NOT the schedule's start-date
  // sort, which would reshuffle the tree whenever estimates/priorities change.
  for (const list of byParent.values()) list.sort((a, b) => a.position - b.position);
  const hasKids = (id: string) => (byParent.get(id) || []).length > 0;

  // ── mutations (each reloads to refresh the recomputed schedule) ──
  const setEstimate = async (id: string, v: string) => { await updateTask(id, { duration: v === '' ? null : Number(v) }); await reload(); };
  const setBuffer = async (id: string, v: string) => { await planner.updateTaskPlanner(id, { bufferHours: v === '' ? 0 : Number(v) }); await reload(); };
  const setAssignee = async (id: string, a: string) => { await planner.updateTaskPlanner(id, { assigneeId: a }); await reload(); };
  const setStatus = async (id: string, s: string) => { await updateTask(id, { status: s }); await reload(); };
  const setPriority = async (id: string, v: string) => { await planner.updateTaskPlanner(id, { plannerPriority: Number(v) }); await reload(); };

  const toggle = (id: string) => setCollapsed((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const collapseAll = () => setCollapsed(new Set(rows.filter((r) => hasKids(r.taskId)).map((r) => r.taskId)));
  const expandAll = () => setCollapsed(new Set());

  // ── inline rename ──
  const saveRename = async () => {
    if (!renaming || !renaming.title.trim()) { setRenaming(null); return; }
    await updateTask(renaming.id, { title: renaming.title.trim() });
    setRenaming(null);
    await reload();
  };

  // ── draft (inline create) ──
  const startDraft = (parentId: string | null) => {
    const parentRow = parentId ? rows.find((r) => r.taskId === parentId) : undefined;
    if (parentId) setCollapsed((prev) => { const n = new Set(prev); n.delete(parentId); return n; });
    setDraft({ parentId, title: '', estimate: '', assigneeId: parentRow?.assigneeId ?? '' });
  };
  const saveDraft = async () => {
    if (!draft || !draft.title.trim()) return;
    const created = await createTask({ title: draft.title.trim(), parentId: draft.parentId });
    if (draft.estimate !== '') await updateTask(created.id, { duration: Number(draft.estimate) });
    if (draft.assigneeId) await planner.updateTaskPlanner(created.id, { assigneeId: draft.assigneeId });
    setDraft(null);
    await reload();
  };

  // ── dependencies ──
  const titleOf = (id: string) => rows.find((r) => r.taskId === id)?.title ?? id.slice(0, 8);
  const openDeps = async (taskId: string) => { setDepsFor(taskId); setDepErr(null); setDeps(await planner.listDependencies(taskId)); };
  const addDep = async (blockerId: string) => {
    if (!depsFor || !blockerId) return;
    try { await planner.createDependency(depsFor, blockerId); setDeps(await planner.listDependencies(depsFor)); setDepErr(null); await reload(); }
    catch { setDepErr('Could not add — that would create a cycle.'); }
  };
  const removeDep = async (id: string) => { await planner.deleteDependency(id); if (depsFor) setDeps(await planner.listDependencies(depsFor)); await reload(); };

  // ── drag to re-parent + reorder ──
  // Position in the row (top 30% = before, bottom 30% = after, middle = into).
  const computeMode = (e: React.DragEvent): 'before' | 'after' | 'into' => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const y = e.clientY - rect.top;
    return y < rect.height * 0.3 ? 'before' : y > rect.height * 0.7 ? 'after' : 'into';
  };
  const move = async (draggedId: string, parentId: string | null, position: number) => {
    setDropTarget(null);
    try { await planner.updateTaskPlanner(draggedId, { parentId: parentId ?? '', position }); await reload(); }
    catch { window.alert('Cannot move there — that would create a cycle.'); }
  };
  const onRowDrop = (e: React.DragEvent, target: ScheduleRow) => {
    e.preventDefault();
    const draggedId = e.dataTransfer.getData('text/plain');
    const mode = computeMode(e);
    setDropTarget(null);
    if (!draggedId || draggedId === target.taskId) return;
    if (mode === 'into') {
      const kids = byParent.get(target.taskId) || [];
      void move(draggedId, target.taskId, kids.length ? Math.max(...kids.map((k) => k.position)) + 1 : target.position);
      return;
    }
    const sibs = byParent.get(target.parentId) || [];
    const idx = sibs.findIndex((s) => s.taskId === target.taskId);
    let pos: number;
    if (mode === 'before') { const prev = sibs[idx - 1]; pos = prev ? (prev.position + target.position) / 2 : target.position - 1; }
    else { const next = sibs[idx + 1]; pos = next ? (target.position + next.position) / 2 : target.position + 1; }
    void move(draggedId, target.parentId, pos);
  };
  const onRootDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const draggedId = e.dataTransfer.getData('text/plain');
    setDropTarget(null);
    if (!draggedId) return;
    const rp = rootId ?? null;
    const roots = byParent.get(rp) || [];
    void move(draggedId, rp, roots.length ? Math.max(...roots.map((r) => r.position)) + 1 : 0);
  };

  const draftRow = (depth: number): React.ReactNode => (
    <tr key="__draft__" className={styles.draftRow}>
      <td style={{ paddingLeft: 8 + depth * 18 }}>
        <span className={styles.toggleSpacer} />
        <input autoFocus className={styles.txt} placeholder="New task title" value={draft!.title}
          onChange={(e) => setDraft({ ...draft!, title: e.target.value })}
          onKeyDown={(e) => { if (e.key === 'Enter') void saveDraft(); if (e.key === 'Escape') setDraft(null); }} />
        <button className={styles.saveBtn} onClick={() => void saveDraft()}>Save</button>
        <button className={styles.addBtn} onClick={() => setDraft(null)}>Cancel</button>
      </td>
      <td><input className={styles.numIn} type="number" min="0" placeholder="h" value={draft!.estimate}
        onChange={(e) => setDraft({ ...draft!, estimate: e.target.value })} /></td>
      <td />
      <td />
      <td>
        <AssigneeSelect value={draft!.assigneeId} people={people} onChange={(v) => setDraft({ ...draft!, assigneeId: v })} />
      </td>
      <td colSpan={4} />
    </tr>
  );

  const renderRows = (parentId: string | null, depth: number): React.ReactNode[] => {
    const kids = byParent.get(parentId) || [];
    const out: React.ReactNode[] = kids.flatMap((r) => {
      const parent = hasKids(r.taskId);
      const isCollapsed = collapsed.has(r.taskId);
      const done = r.status === 'CLOSED';
      const row = (
        <tr key={r.taskId}
          className={[
            r.onCriticalPath ? styles.critical : '',
            dropTarget && dropTarget.id === r.taskId ? styles[`drop_${dropTarget.mode}`] : '',
          ].filter(Boolean).join(' ')}
          draggable
          onDragStart={(e) => e.dataTransfer.setData('text/plain', r.taskId)}
          onDragOver={(e) => { e.preventDefault(); setDropTarget({ id: r.taskId, mode: computeMode(e) }); }}
          onDragLeave={() => setDropTarget((d) => (d?.id === r.taskId ? null : d))}
          onDragEnd={() => setDropTarget(null)}
          onDrop={(e) => onRowDrop(e, r)}>
          <td style={{ paddingLeft: 8 + depth * 18 }}>
            <div className={styles.titleRow}>
              {parent ? (
                <button className={styles.toggle} onClick={() => toggle(r.taskId)}>{isCollapsed ? '▸' : '▾'}</button>
              ) : (
                <span className={styles.toggleSpacer} />
              )}
              <div className={styles.titleCol}>
                {renaming?.id === r.taskId ? (
                  <input autoFocus className={styles.txt} style={{ width: '100%' }} value={renaming.title}
                    onChange={(e) => setRenaming({ id: r.taskId, title: e.target.value })}
                    onBlur={() => void saveRename()}
                    onKeyDown={(e) => { if (e.key === 'Enter') void saveRename(); if (e.key === 'Escape') setRenaming(null); }} />
                ) : (
                  <span className={`${styles.taskLink} ${styles.titleFull} ${done ? styles.done : ''}`}
                    onClick={() => navigate(`/projects/${r.taskId}`)}
                    onDoubleClick={() => setRenaming({ id: r.taskId, title: r.title })}
                    title="click: open · double-click: rename">{r.title}</span>
                )}
                <div className={styles.metaRow}>
                  {r.dependencyCount > 0 && <span className={styles.depBadge} title={`blocked by ${r.dependencyCount}`}>⛓{r.dependencyCount}</span>}
                  <span className={styles.rowActions}>
                    <button className={styles.iconBtn} title="Add subtask" onClick={() => startDraft(r.taskId)}>＋</button>
                    <button className={styles.iconBtn} title="Add sibling" onClick={() => startDraft(r.parentId)}>↳</button>
                    <button className={styles.iconBtn} title="Dependencies" onClick={() => openDeps(r.taskId)}>⛓</button>
                  </span>
                </div>
              </div>
            </div>
          </td>
          <td>
            {parent ? <span className={styles.muted}>{r.estimateHours ?? '—'}</span>
              : <input className={styles.numIn} type="number" min="0" defaultValue={r.estimateHours ?? ''} onBlur={(e) => setEstimate(r.taskId, e.target.value)} />}
          </td>
          <td>
            {parent ? <input className={styles.numIn} type="number" min="0" placeholder="0" defaultValue={r.bufferHours ?? ''} onBlur={(e) => setBuffer(r.taskId, e.target.value)} title="Buffer (hours)" />
              : null}
          </td>
          <td>
            <input className={styles.numIn} type="number" step="0.1" defaultValue={r.priority || ''}
              onBlur={(e) => setPriority(r.taskId, e.target.value)} title="Priority (fractional)" />
          </td>
          <td>
            <AssigneeSelect value={r.assigneeId ?? ''} people={people} onChange={(v) => setAssignee(r.taskId, v)} />
          </td>
          <td>
            <StatusSelect value={r.status} onChange={(v) => setStatus(r.taskId, v)} />
          </td>
          <td className={styles.date}>{r.start || '—'}</td>
          <td className={styles.date}>{r.end || '—'}</td>
          <td className={styles.cp}>{r.onCriticalPath ? '★' : ''}</td>
        </tr>
      );
      // Recurse to render children, OR to surface a pending draft child even on a
      // currently-childless row (so the row-level ＋ works for the *first* subtask).
      const showChildren = (parent || draft?.parentId === r.taskId) && !isCollapsed;
      return showChildren ? [row, ...renderRows(r.taskId, depth + 1)] : [row];
    });
    if (draft && draft.parentId === parentId) out.push(draftRow(depth));
    return out;
  };

  if (loading) return <p className={styles.muted}>Loading…</p>;

  const start = rootId ?? null;
  const topKids = byParent.get(start) || [];
  return (
    <div>
      <div className={styles.treeToolbar}>
        <button className={styles.primary} onClick={() => startDraft(start)}>+ {rootId ? 'Subtask' : 'Project'}</button>
        <button className={styles.addBtn} onClick={collapseAll}>Collapse all</button>
        <button className={styles.addBtn} onClick={expandAll}>Expand all</button>
        {!rootId && (
          <span
            className={styles.rootDrop}
            onDragOver={(e) => e.preventDefault()}
            onDrop={onRootDrop}
            title="Drop a task here to move it to the top level"
          >drop here to make top-level</span>
        )}
      </div>
      <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th><span className={styles.tip} data-tip="Click a title to open · double-click to rename · drag a row to move it (drop near top/bottom = reorder, drop onto a row = make it a child).">Task</span></th>
            <th><span className={styles.tip} data-tip="Estimate in hours, on leaf tasks. Parents show the rolled-up sum of their descendants.">Estimate</span></th>
            <th><span className={styles.tip} data-tip="Buffer / contingency hours added on a parent task, on top of its children's total.">Buffer</span></th>
            <th><span className={styles.tip} data-tip="Priority — your own fractional ranking (lower = higher), also used as the scheduler tie-break.">Priority</span></th>
            <th><span className={styles.tip} data-tip="The person doing this task. New subtasks inherit the parent's assignee.">Assignee</span></th>
            <th><span className={styles.tip} data-tip="To do / In progress / Done. Done tasks stay visible but are excluded from scheduling.">Status</span></th>
            <th><span className={styles.tip} data-tip="Computed start date — derived from estimates, dependencies, and assignee availability.">Start</span></th>
            <th><span className={`${styles.tip} ${styles.tipRight}`} data-tip="Computed end date.">End</span></th>
            <th><span className={`${styles.tip} ${styles.tipRight}`} data-tip="★ marks the critical path: the chain of tasks that determines the project's end date.">Critical Path</span></th>
          </tr>
        </thead>
        <tbody>{renderRows(start, 0)}</tbody>
      </table>
      </div>
      {topKids.length === 0 && (
        <p className={styles.muted}>{rootId ? 'No subtasks yet.' : 'No tasks yet. Add a project to begin.'}</p>
      )}

      {depsFor && (
        <div className={styles.overlay} onClick={() => setDepsFor(null)}>
          <div className={styles.popup} onClick={(e) => e.stopPropagation()}>
            <h3>Blocked by — {titleOf(depsFor)}</h3>
            {deps.length === 0 && <p className={styles.muted}>No dependencies yet.</p>}
            {deps.map((d) => (
              <div key={d.id} className={styles.depRow}>
                <span>{titleOf(d.dependsOnId)}</span>
                <button className={styles.danger} onClick={() => removeDep(d.id)}>×</button>
              </div>
            ))}
            <div className={styles.formRow}>
              <Select value="" onValueChange={(v) => { void addDep(v); }}>
                <SelectTrigger className="h-8 w-full text-[13px]"><SelectValue placeholder="+ add blocker…" /></SelectTrigger>
                <SelectContent>
                  {rows.filter((r) => r.taskId !== depsFor && !deps.some((d) => d.dependsOnId === r.taskId))
                    .map((r) => <SelectItem key={r.taskId} value={r.taskId}>{r.title}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {depErr && <p className={styles.error}>{depErr}</p>}
            <button className={styles.primary} onClick={() => setDepsFor(null)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
