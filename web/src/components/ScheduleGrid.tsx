import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import * as planner from '../api/planner';
import type { ScheduleRow, CalendarObj, Holiday } from '../api/planner';
import { cn } from '@/lib/utils';

const todayStr = () => new Date().toISOString().slice(0, 10);
const fmtRow = (d: string) => new Date(d + 'T00:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
function weekendBit(d: string, mask: number) {
  const js = new Date(d + 'T00:00:00Z').getUTCDay(); // Sun=0..Sat=6
  const bit = 1 << ((js + 6) % 7); // Mon=1..Sun=64
  return (mask & bit) !== 0;
}
function addDays(d: string, n: number) {
  const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}

/** Assignee × date schedule grid. rootId scopes the *display* to a subtree;
 *  dates are always the engine's portfolio-wide result. */
export default function ScheduleGrid({ rootId }: { rootId?: string }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [cal, setCal] = useState<CalendarObj | null>(null);
  const [holidays, setHolidays] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
    (async () => {
      const [s, c] = await Promise.all([planner.getSchedule(), planner.getCalendar()]);
      const hs = await planner.listHolidays(c.id);
      setRows(s); setCal(c); setHolidays(new Set(hs.map((h: Holiday) => h.day))); setLoading(false);
    })().catch(() => setLoading(false));
  }, []);

  const model = useMemo(() => {
    const byId = new Map(rows.map((r) => [r.taskId, r]));
    const hasKids = new Set(rows.map((r) => r.parentId).filter(Boolean) as string[]);
    const isLeaf = (id: string) => !hasKids.has(id);
    const rootTitle = (id: string): string => {
      let r = byId.get(id); let last = r?.title ?? '';
      while (r && r.parentId) { r = byId.get(r.parentId); if (r) last = r.title; }
      return last;
    };
    const inScope = (r: ScheduleRow): boolean => {
      if (!rootId) return true;
      let cur: ScheduleRow | undefined = r;
      while (cur) { if (cur.taskId === rootId) return true; cur = cur.parentId ? byId.get(cur.parentId) : undefined; }
      return false;
    };
    const leaves = rows.filter((r) => r.start && isLeaf(r.taskId) && inScope(r));
    const people = [...new Set(leaves.map((l) => l.assigneeName || 'Unassigned'))];
    const starts = leaves.map((l) => l.start).filter(Boolean).sort();
    const ends = leaves.map((l) => l.end).filter(Boolean).sort();
    const dates: string[] = [];
    if (starts.length) {
      let d = starts[0];
      const end = ends[ends.length - 1];
      for (let i = 0; d <= end && i < 400; i++) { dates.push(d); d = addDays(d, 1); }
    }
    const cellTasks = (person: string, date: string) =>
      leaves.filter((l) => (l.assigneeName || 'Unassigned') === person && l.start <= date && date <= l.end);
    return { people, dates, cellTasks, rootTitle };
  }, [rows, rootId]);

  if (loading) return (
    <div className="space-y-2">
      <div className="h-9 w-full animate-pulse rounded-md bg-muted" />
      {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-11 w-full animate-pulse rounded-md bg-muted/50" />)}
    </div>
  );
  if (model.people.length === 0) return <p className="text-sm text-muted-foreground">Nothing scheduled yet — give tasks an estimate and an assignee.</p>;

  const mask = cal?.weekendDays ?? 96;
  const today = todayStr();

  const exportCsv = () => {
    const cell = (v: unknown) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const lines = ['Assignee,Task,Project,Start,End,Estimate (h),Critical Path,Jira URL'];
    for (const p of model.people) {
      const seen = new Set<string>();
      for (const d of model.dates) for (const t of model.cellTasks(p, d)) {
        if (seen.has(t.taskId)) continue; seen.add(t.taskId);
        lines.push([p, t.title, model.rootTitle(t.taskId), t.start, t.end, t.estimateHours ?? '', t.onCriticalPath ? 'yes' : '', t.jiraUrl ?? ''].map(cell).join(','));
      }
    }
    const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    const a = document.createElement('a'); a.href = url; a.download = `schedule-${today}.csv`; a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-end">
        <button onClick={exportCsv} className="inline-flex h-[34px] items-center gap-1.5 rounded-md border px-3 text-[13px] font-medium hover:bg-muted">
          ↓ Export CSV
        </button>
      </div>
      <div className="overflow-auto rounded-xl border">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 w-[130px] border-b bg-muted px-3 py-2.5 text-left text-[12.5px] font-medium text-muted-foreground">Date</th>
              {model.people.map((p) => (
                <th key={p} className="min-w-[190px] border-b border-l bg-muted px-3 py-2.5 text-left text-[12.5px] font-medium">{p}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {model.dates.map((d) => {
              const wknd = weekendBit(d, mask) || holidays.has(d);
              const isToday = d === today;
              return (
                <tr key={d} className={cn(wknd && 'bg-muted/50', isToday && 'shadow-[inset_0_2px_0_0_var(--color-foreground)]')}>
                  <td className={cn('w-[130px] whitespace-nowrap border-b px-3 py-1.5 align-top text-[12.5px] tabular-nums', wknd ? 'text-muted-foreground' : 'text-muted-foreground', isToday && 'font-semibold text-foreground')}>
                    {fmtRow(d)}{isToday && ' · today'}
                  </td>
                  {model.people.map((p) => {
                    const tasks = model.cellTasks(p, d);
                    return (
                      <td key={p} className="min-w-[190px] border-b border-l px-2 py-1 align-top">
                        {wknd && tasks.length === 0 ? (
                          <span className="text-[11.5px] text-muted-foreground/70">weekend</span>
                        ) : (
                          tasks.map((t) => (
                            <button
                              key={t.taskId}
                              onClick={() => navigate(`/projects/${t.taskId}`)}
                              title="Open task"
                              className={cn('my-0.5 block w-full rounded-md border border-l-[3px] bg-muted px-2 py-1 text-left text-[12px] transition-colors hover:bg-accent', t.onCriticalPath ? 'border-l-destructive' : 'border-l-muted-foreground/40')}
                            >
                              <div className="flex items-baseline justify-between gap-2">
                                <span className="font-medium">{t.title}</span>
                                {t.estimateHours != null && <span className="shrink-0 text-[10.5px] tabular-nums text-muted-foreground">{t.estimateHours}h</span>}
                              </div>
                              <div className="text-[10.5px] text-muted-foreground">{model.rootTitle(t.taskId)}</div>
                            </button>
                          ))
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
