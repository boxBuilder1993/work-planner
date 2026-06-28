import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { createTask, updateTask } from '../api/tasks';
import * as planner from '../api/planner';
import type { Person, ScheduleRow } from '../api/planner';
import styles from './Planner.module.css';

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

  const reload = useCallback(async () => {
    const [s, p] = await Promise.all([planner.getSchedule(), planner.listPeople()]);
    setRows(s);
    setPeople(p);
    setLoading(false);
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => { localStorage.setItem(collapseKey, JSON.stringify([...collapsed])); }, [collapsed, collapseKey]);

  const byParent = new Map<string | null, ScheduleRow[]>();
  for (const r of rows) {
    const k = r.parentId;
    if (!byParent.has(k)) byParent.set(k, []);
    byParent.get(k)!.push(r);
  }
  const hasKids = (id: string) => (byParent.get(id) || []).length > 0;

  // ── mutations (each reloads to refresh the recomputed schedule) ──
  const setEstimate = async (id: string, v: string) => { await updateTask(id, { duration: v === '' ? null : Number(v) }); await reload(); };
  const setBuffer = async (id: string, v: string) => { await planner.updateTaskPlanner(id, { bufferHours: v === '' ? 0 : Number(v) }); await reload(); };
  const setAssignee = async (id: string, a: string) => { await planner.updateTaskPlanner(id, { assigneeId: a }); await reload(); };
  const setStatus = async (id: string, s: string) => { await updateTask(id, { status: s }); await reload(); };

  const toggle = (id: string) => setCollapsed((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
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

  // ── drag to re-parent ──
  const reparent = async (childId: string, parentId: string | null) => {
    if (childId === parentId) return;
    try { await planner.updateTaskPlanner(childId, { parentId: parentId ?? '' }); await reload(); }
    catch { window.alert('Cannot move there — that would create a cycle.'); }
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
      <td>
        <select className={styles.sel} value={draft!.assigneeId} onChange={(e) => setDraft({ ...draft!, assigneeId: e.target.value })}>
          <option value="">— unassigned —</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
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
        <tr key={r.taskId} className={r.onCriticalPath ? styles.critical : undefined}
          draggable
          onDragStart={(e) => e.dataTransfer.setData('text/plain', r.taskId)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { const id = e.dataTransfer.getData('text/plain'); if (id) void reparent(id, r.taskId); }}>
          <td style={{ paddingLeft: 8 + depth * 18 }}>
            {parent ? (
              <button className={styles.toggle} onClick={() => toggle(r.taskId)}>{isCollapsed ? '▸' : '▾'}</button>
            ) : (
              <span className={styles.toggleSpacer} />
            )}
            {renaming?.id === r.taskId ? (
              <input autoFocus className={styles.txt} value={renaming.title}
                onChange={(e) => setRenaming({ id: r.taskId, title: e.target.value })}
                onBlur={() => void saveRename()}
                onKeyDown={(e) => { if (e.key === 'Enter') void saveRename(); if (e.key === 'Escape') setRenaming(null); }} />
            ) : (
              <span className={`${styles.taskLink} ${done ? styles.done : ''}`}
                onClick={() => navigate(`/tasks/${r.taskId}`)}
                onDoubleClick={() => setRenaming({ id: r.taskId, title: r.title })}
                title="click: open · double-click: rename">{r.title}</span>
            )}
            {r.dependencyCount > 0 && <span className={styles.depBadge} title={`blocked by ${r.dependencyCount}`}>⛓{r.dependencyCount}</span>}
            <span className={styles.rowActions}>
              <button className={styles.iconBtn} title="Add subtask" onClick={() => startDraft(r.taskId)}>＋</button>
              <button className={styles.iconBtn} title="Add sibling" onClick={() => startDraft(r.parentId)}>↳</button>
              <button className={styles.iconBtn} title="Dependencies" onClick={() => openDeps(r.taskId)}>⛓</button>
            </span>
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
            <select className={styles.sel} value={r.assigneeId ?? ''} onChange={(e) => setAssignee(r.taskId, e.target.value)}>
              <option value="">— unassigned —</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </td>
          <td>
            <select className={styles.statusSel} value={r.status} onChange={(e) => setStatus(r.taskId, e.target.value)}>
              <option value="PENDING">To do</option>
              <option value="IN_PROGRESS">In progress</option>
              <option value="CLOSED">Done</option>
            </select>
          </td>
          <td className={styles.date}>{r.start || '—'}</td>
          <td className={styles.date}>{r.end || '—'}</td>
          <td className={styles.cp}>{r.onCriticalPath ? '★' : ''}</td>
        </tr>
      );
      return parent && !isCollapsed ? [row, ...renderRows(r.taskId, depth + 1)] : [row];
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
        <span
          className={styles.rootDrop}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { const id = e.dataTransfer.getData('text/plain'); if (id) void reparent(id, start); }}
        >drop here to make top-level</span>
      </div>
      <table className={styles.table}>
        <thead>
          <tr><th>Task</th><th>Est</th><th>Buf</th><th>Assignee</th><th>Status</th><th>Start</th><th>End</th><th>CP</th></tr>
        </thead>
        <tbody>{renderRows(start, 0)}</tbody>
      </table>
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
              <select className={styles.sel} value="" onChange={(e) => { void addDep(e.target.value); }}>
                <option value="">+ add blocker…</option>
                {rows.filter((r) => r.taskId !== depsFor && !deps.some((d) => d.dependsOnId === r.taskId))
                  .map((r) => <option key={r.taskId} value={r.taskId}>{r.title}</option>)}
              </select>
            </div>
            {depErr && <p className={styles.error}>{depErr}</p>}
            <button className={styles.primary} onClick={() => setDepsFor(null)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
