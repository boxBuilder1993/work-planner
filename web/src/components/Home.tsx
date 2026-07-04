import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import * as planner from '../api/planner';
import type { ScheduleRow } from '../api/planner';
import { cn } from '@/lib/utils';

type Health = 'on-track' | 'at-risk' | 'late' | 'unscheduled';

const HEALTH: Record<Health, { label: string; dot: string }> = {
  'on-track': { label: 'On track', dot: 'bg-green-600' },
  'at-risk': { label: 'At risk', dot: 'bg-amber-500' },
  late: { label: 'Late', dot: 'bg-destructive' },
  unscheduled: { label: 'Unscheduled', dot: 'bg-muted-foreground' },
};

function initials(name?: string | null): string {
  if (!name) return '?';
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? p[0]?.[1] ?? '')).toUpperCase();
}
function fmtDate(d: string): string {
  if (!d) return '—';
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function Home() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
    planner.getSchedule().then((r) => { setRows(r); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const byParent = new Map<string | null, ScheduleRow[]>();
  for (const r of rows) { const k = r.parentId; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k)!.push(r); }
  const isLeaf = (id: string) => (byParent.get(id) || []).length === 0;

  const collectLeaves = (id: string): ScheduleRow[] => {
    const out: ScheduleRow[] = [];
    for (const k of byParent.get(id) || []) {
      if (isLeaf(k.taskId)) out.push(k); else out.push(...collectLeaves(k.taskId));
    }
    return out;
  };
  const health = (eta: string, dueMs: number | null): Health => {
    if (!eta) return 'unscheduled';
    if (!dueMs) return 'on-track';
    const due = new Date(dueMs).toISOString().slice(0, 10);
    if (eta > due) return 'late';
    if ((new Date(due).getTime() - new Date(eta).getTime()) / 86400000 <= 3) return 'at-risk';
    return 'on-track';
  };

  const roots = byParent.get(null) || [];
  const projects = roots.map((p) => {
    const leaves = collectLeaves(p.taskId);
    const team = [...new Set(leaves.map((l) => l.assigneeName).filter(Boolean))] as string[];
    return {
      row: p,
      total: leaves.length,
      done: leaves.filter((l) => l.status === 'CLOSED').length,
      team,
      eta: p.end,
      health: health(p.end, p.dueDate),
    };
  });

  // portfolio strip
  const attention = projects.filter((p) => p.health === 'at-risk' || p.health === 'late').length;
  const portfolioEta = projects.map((p) => p.eta).filter(Boolean).sort().pop() || '';
  const load = new Map<string, number>();
  for (const r of rows) {
    if (!isLeaf(r.taskId) || r.status === 'CLOSED' || !r.assigneeName) continue;
    load.set(r.assigneeName, (load.get(r.assigneeName) || 0) + (r.estimateHours || 0));
  }
  const mostLoaded = [...load.entries()].sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <h1 className="text-[19px] font-semibold tracking-tight">Projects</h1>
        <div className="flex-1" />
        <button className="inline-flex h-[34px] items-center rounded-md bg-primary px-3 text-[13px] font-medium text-primary-foreground">
          + New project
        </button>
      </header>

      <div className="p-7">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <div className="mb-5 flex flex-wrap gap-4">
              <Stat n={String(projects.length)} l="Active projects" />
              <Stat n={String(attention)} l="At risk / late" accent={attention > 0} />
              <Stat n={portfolioEta ? fmtDate(portfolioEta) : '—'} l="Portfolio ETA" />
              <Stat n={mostLoaded ? mostLoaded[0] : '—'} l={mostLoaded ? `Most loaded · ${mostLoaded[1]}h` : 'Most loaded'} />
            </div>

            <div className="overflow-hidden rounded-xl border">
              {projects.length === 0 && <p className="p-6 text-sm text-muted-foreground">No projects yet. Create one to begin.</p>}
              {projects.map(({ row, total, done, team, eta, health: h }) => (
                <button
                  key={row.taskId}
                  onClick={() => navigate(`/tasks/${row.taskId}`)}
                  className="grid w-full grid-cols-[1.6fr_130px_110px_130px_130px] items-center gap-4 border-b px-[18px] py-4 text-left last:border-b-0 hover:bg-muted"
                >
                  <div>
                    <div className="text-[14.5px] font-semibold">{row.title}</div>
                    <div className="text-[12.5px] text-muted-foreground">{total} tasks · {done} done</div>
                  </div>
                  <div className="h-1.5 w-[120px] overflow-hidden rounded-full bg-border">
                    <div className="h-full bg-foreground" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
                  </div>
                  <div className="flex">
                    {team.slice(0, 3).map((t, i) => (
                      <span key={t} className={cn('inline-flex size-6 items-center justify-center rounded-full border-[1.5px] border-background bg-muted text-[11px] font-semibold text-muted-foreground', i > 0 && '-ml-1.5')}>
                        {initials(t)}
                      </span>
                    ))}
                  </div>
                  <div className="text-[13px] text-muted-foreground">ETA <span className="font-semibold text-foreground">{fmtDate(eta)}</span></div>
                  <div>
                    <span className="inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-[12px] font-medium text-muted-foreground">
                      <span className={cn('size-[7px] rounded-full', HEALTH[h].dot)} /> {HEALTH[h].label}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ n, l, accent }: { n: string; l: string; accent?: boolean }) {
  return (
    <div className="min-w-[130px] rounded-[10px] border px-4 py-3">
      <div className={cn('text-[22px] font-semibold tracking-tight', accent && 'text-destructive')}>{n}</div>
      <div className="mt-0.5 text-[12px] text-muted-foreground">{l}</div>
    </div>
  );
}
