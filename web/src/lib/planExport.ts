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

/** Build and download an .xlsx plan snapshot: a Summary tab (assignee capacity +
 *  team total) and one tab per assignee (a row per level-3 task they work on). */
export function exportPlan(ctx: PlanExportCtx, filename: string) {
  const { rows, people, timeOff, weekendMask, holidays } = ctx;
  const byId = new Map(rows.map((r) => [r.taskId, r]));
  const hasKids = new Set(rows.map((r) => r.parentId).filter(Boolean) as string[]);
  const isLeaf = (id: string) => !hasKids.has(id);
  const level = (id: string): number => { let n = 1; let r = byId.get(id); while (r && r.parentId) { const p = byId.get(r.parentId); if (!p) break; r = p; n++; } return n; };
  const rootTitle = (id: string): string => { let r = byId.get(id); let last = r?.title ?? ''; while (r && r.parentId) { const p = byId.get(r.parentId); if (!p) break; last = p.title; r = p; } return last; };
  const pathTo = (id: string): string => { const names: string[] = []; let r = byId.get(id); while (r) { names.unshift(r.title); r = r.parentId ? byId.get(r.parentId) : undefined; } return names.join(' › '); };
  // Fold anything deeper than level 3 into its level-3 ancestor.
  const bucketOf = (id: string): string => { let cur = id; let guard = 0; while (level(cur) > 3 && guard++ < 50) { const p = byId.get(cur)?.parentId; if (!p) break; cur = p; } return cur; };

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

  // Assigned hours per assignee (from leaves), and per-(assignee,L3-bucket) hours.
  const assigned = new Map<string, number>();               // assigneeId -> total hours
  const byPersonBucket = new Map<string, Map<string, number>>(); // assigneeId -> (bucketId -> hours)
  const unassignedBucket = new Map<string, number>();
  for (const l of leaves) {
    const h = l.estimateHours ?? 0;
    const bucket = bucketOf(l.taskId);
    if (l.assigneeId) {
      assigned.set(l.assigneeId, (assigned.get(l.assigneeId) ?? 0) + h);
      if (!byPersonBucket.has(l.assigneeId)) byPersonBucket.set(l.assigneeId, new Map());
      const m = byPersonBucket.get(l.assigneeId)!;
      m.set(bucket, (m.get(bucket) ?? 0) + h);
    } else {
      unassignedBucket.set(bucket, (unassignedBucket.get(bucket) ?? 0) + h);
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

  // ── Summary ──
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
  summary.push([]);
  summary.push(['Team total', round(teamAssigned), round(teamAvail), pct(teamAvail ? teamAssigned / teamAvail : Infinity), teamAssigned > teamAvail ? 'Overloaded' : 'OK']);
  const unassignedHours = [...unassignedBucket.values()].reduce((s, x) => s + x, 0);
  if (unassignedHours > 0) summary.push([], ['Unassigned (h)', round(unassignedHours)]);
  const ws0 = XLSX.utils.aoa_to_sheet(summary);
  ws0['!cols'] = [{ wch: 22 }, { wch: 13 }, { wch: 14 }, { wch: 12 }, { wch: 12 }];
  XLSX.utils.book_append_sheet(wb, ws0, sheetName('Summary'));

  // ── One tab per assignee: a row per level-3 task ──
  const header = ['Project', 'Task', 'Path', 'Hours', 'Start', 'End', 'Due', 'Status', 'Critical', 'Jira URL'];
  const bucketRows = (buckets: Map<string, number>): (string | number)[][] => {
    const list = [...buckets.entries()].map(([id, h]) => ({ r: byId.get(id), h })).filter((x) => x.r);
    list.sort((a, b) => (a.r!.start || '').localeCompare(b.r!.start || ''));
    const out = list.map(({ r, h }) => [
      rootTitle(r!.taskId), r!.title, pathTo(r!.taskId), round(h),
      r!.start || '', r!.end || '', msToYMD(r!.dueDate), r!.status,
      r!.onCriticalPath ? '★' : '', r!.jiraUrl ?? '',
    ]);
    return out;
  };
  const cols = [{ wch: 20 }, { wch: 26 }, { wch: 34 }, { wch: 8 }, { wch: 12 }, { wch: 12 }, { wch: 12 }, { wch: 12 }, { wch: 9 }, { wch: 40 }];
  for (const p of workers) {
    const rowsA = bucketRows(byPersonBucket.get(p.id)!);
    const total = round((assigned.get(p.id) ?? 0));
    const aoa = [header, ...rowsA, [], ['', '', 'Total', total]];
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    ws['!cols'] = cols;
    XLSX.utils.book_append_sheet(wb, ws, sheetName(p.name));
  }
  if (unassignedHours > 0) {
    const ws = XLSX.utils.aoa_to_sheet([header, ...bucketRows(unassignedBucket)]);
    ws['!cols'] = cols;
    XLSX.utils.book_append_sheet(wb, ws, sheetName('Unassigned'));
  }

  XLSX.writeFile(wb, filename);
}

function round(n: number): number { return Math.round(n * 100) / 100; }
