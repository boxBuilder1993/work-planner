import * as XLSX from 'xlsx';
import type { ScheduleRow, Person, TimeOffEntry } from '../api/planner';

export type PlanExportCtx = {
  rows: ScheduleRow[];
  people: Person[];
  timeOff: Record<string, TimeOffEntry[]>; // personId -> entries
  weekendMask: number;
  holidays: Set<string>;
};

const parse = (s: string) => new Date(s + 'T00:00:00Z');
const addDays = (s: string, n: number) => { const t = parse(s); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
const isWeekend = (s: string, mask: number) => (mask & (1 << ((parse(s).getUTCDay() + 6) % 7))) !== 0;
const msToYMD = (ms: number | null) => (ms == null ? '' : new Date(ms).toISOString().slice(0, 10));
const pct = (n: number) => (isFinite(n) ? Math.round(n * 100) + '%' : '—');
const round = (n: number) => Math.round(n * 100) / 100;

/** Build and download an .xlsx plan snapshot: a Summary tab (assignee capacity +
 *  team total), one tab per assignee (a row per leaf task they own, with the
 *  hierarchy shown no deeper than level 3), and a Dependencies tab. */
export function exportPlan(ctx: PlanExportCtx, filename: string) {
  const { rows, people, timeOff, weekendMask, holidays } = ctx;
  const byId = new Map(rows.map((r) => [r.taskId, r]));
  const hasKids = new Set(rows.map((r) => r.parentId).filter(Boolean) as string[]);
  const isLeaf = (id: string) => !hasKids.has(id);
  const rootTitle = (id: string): string => { let r = byId.get(id); let last = r?.title ?? ''; while (r && r.parentId) { const p = byId.get(r.parentId); if (!p) break; last = p.title; r = p; } return last; };
  // Ancestor chain (root → the task's parent), capped to the first 3 levels — so
  // the displayed hierarchy never goes deeper than level 3.
  const cappedPath = (id: string): string => {
    const chain: string[] = [];
    let r = byId.get(id);
    while (r && r.parentId) { const p = byId.get(r.parentId); if (!p) break; chain.unshift(p.title); r = p; }
    return chain.slice(0, 3).join(' › ');
  };

  const leaves = rows.filter((r) => r.start && isLeaf(r.taskId));
  const starts = leaves.map((l) => l.start).filter(Boolean).sort();
  const ends = leaves.map((l) => l.end).filter(Boolean).sort();
  const hStart = starts[0] ?? '';
  const hEnd = ends[ends.length - 1] ?? '';

  const availableFor = (personId: string): number => {
    const p = people.find((x) => x.id === personId);
    if (!p || !hStart) return 0;
    const offs = timeOff[personId] || [];
    let total = 0, d = hStart, guard = 0;
    while (d <= hEnd && guard++ < 2000) {
      if (!isWeekend(d, weekendMask) && !holidays.has(d)) {
        let h = p.hoursPerDay;
        for (const o of offs) if (o.startDay <= d && d <= o.endDay) { if (o.hoursOff == null) h = 0; else h -= o.hoursOff; }
        total += Math.max(0, h);
      }
      d = addDays(d, 1);
    }
    return total;
  };

  // Group leaves by assignee (+ unassigned); assigned hours per person.
  const assigned = new Map<string, number>();
  const leavesByPerson = new Map<string, ScheduleRow[]>();
  const unassignedLeaves: ScheduleRow[] = [];
  for (const l of leaves) {
    if (l.assigneeId) {
      assigned.set(l.assigneeId, (assigned.get(l.assigneeId) ?? 0) + (l.estimateHours ?? 0));
      if (!leavesByPerson.has(l.assigneeId)) leavesByPerson.set(l.assigneeId, []);
      leavesByPerson.get(l.assigneeId)!.push(l);
    } else {
      unassignedLeaves.push(l);
    }
  }

  const wb = XLSX.utils.book_new();
  const usedNames = new Set<string>();
  const sheetName = (raw: string) => {
    let n = (raw || 'Sheet').replace(/[\\/?*[\]:]/g, '-').slice(0, 28).trim() || 'Sheet';
    const base = n;
    let i = 2;
    while (usedNames.has(n.toLowerCase())) n = `${base.slice(0, 25)} ${i++}`;
    usedNames.add(n.toLowerCase());
    return n;
  };

  // ── Summary: assignee capacity + team total ──
  const workers = people.filter((p) => (assigned.get(p.id) ?? 0) > 0);
  let teamAssigned = 0, teamAvail = 0;
  const summary: (string | number)[][] = [
    ['Plan snapshot'],
    [`Horizon: ${hStart || '—'} → ${hEnd || '—'}`],
    [],
    ['Assignee', 'Assigned (h)', 'Available (h)', 'Utilization', 'Status'],
  ];
  for (const p of workers) {
    const a = assigned.get(p.id) ?? 0;
    const av = availableFor(p.id);
    teamAssigned += a; teamAvail += av;
    summary.push([p.name, round(a), round(av), pct(av ? a / av : Infinity), a > av ? 'Overloaded' : 'OK']);
  }
  summary.push([], ['Team total', round(teamAssigned), round(teamAvail), pct(teamAvail ? teamAssigned / teamAvail : Infinity), teamAssigned > teamAvail ? 'Overloaded' : 'OK']);
  const unassignedHours = unassignedLeaves.reduce((s, l) => s + (l.estimateHours ?? 0), 0);
  if (unassignedHours > 0) summary.push([], ['Unassigned (h)', round(unassignedHours)]);
  const ws0 = XLSX.utils.aoa_to_sheet(summary);
  ws0['!cols'] = [{ wch: 22 }, { wch: 13 }, { wch: 14 }, { wch: 12 }, { wch: 12 }];
  XLSX.utils.book_append_sheet(wb, ws0, sheetName('Summary'));

  // ── One tab per assignee: a row per leaf task (hierarchy capped at L3) ──
  const header = ['Project', 'Task', 'Path (≤L3)', 'Hours', 'Start', 'End', 'Due', 'Status', 'Critical', 'Jira URL'];
  const leafRows = (list: ScheduleRow[]): (string | number)[][] =>
    [...list].sort((a, b) => (a.start || '').localeCompare(b.start || '')).map((r) => [
      rootTitle(r.taskId), r.title, cappedPath(r.taskId), round(r.estimateHours ?? 0),
      r.start || '', r.end || '', msToYMD(r.dueDate), r.status, r.onCriticalPath ? '★' : '', r.jiraUrl ?? '',
    ]);
  const cols = [{ wch: 20 }, { wch: 26 }, { wch: 34 }, { wch: 8 }, { wch: 12 }, { wch: 12 }, { wch: 12 }, { wch: 12 }, { wch: 9 }, { wch: 40 }];
  for (const p of workers) {
    const aoa = [header, ...leafRows(leavesByPerson.get(p.id)!), [], ['', '', 'Total', round(assigned.get(p.id) ?? 0)]];
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    ws['!cols'] = cols;
    XLSX.utils.book_append_sheet(wb, ws, sheetName(p.name));
  }
  if (unassignedLeaves.length) {
    const ws = XLSX.utils.aoa_to_sheet([header, ...leafRows(unassignedLeaves)]);
    ws['!cols'] = cols;
    XLSX.utils.book_append_sheet(wb, ws, sheetName('Unassigned'));
  }

  // ── Dependencies: one row per blocker edge (finish-to-start) ──
  const depRows: (string | number)[][] = [['Task', 'Project', 'Blocked by', 'Blocker project', 'Task start', 'Blocker end']];
  for (const r of rows) {
    for (const bid of r.blockedBy || []) {
      const b = byId.get(bid);
      depRows.push([r.title, rootTitle(r.taskId), b?.title ?? bid, b ? rootTitle(bid) : '', r.start || '', b?.end || '']);
    }
  }
  if (depRows.length > 1) {
    const wsd = XLSX.utils.aoa_to_sheet(depRows);
    wsd['!cols'] = [{ wch: 26 }, { wch: 20 }, { wch: 26 }, { wch: 20 }, { wch: 12 }, { wch: 12 }];
    XLSX.utils.book_append_sheet(wb, wsd, sheetName('Dependencies'));
  }

  XLSX.writeFile(wb, filename);
}
