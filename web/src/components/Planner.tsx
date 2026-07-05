import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import * as planner from '../api/planner';
import type { Person, Holiday, ScheduleRow, TimeOffEntry } from '../api/planner';
import PlanTree from './PlanTree';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft } from 'lucide-react';
import styles from './Planner.module.css';

type Tab = 'plan' | 'schedule' | 'team';

const WEEKDAYS = [
  { label: 'Mon', bit: 1 }, { label: 'Tue', bit: 2 }, { label: 'Wed', bit: 4 },
  { label: 'Thu', bit: 8 }, { label: 'Fri', bit: 16 }, { label: 'Sat', bit: 32 }, { label: 'Sun', bit: 64 },
];

export default function Planner() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('plan');
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([planner.getSchedule(), planner.listPeople()]);
      setRows(s);
      setPeople(p);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b bg-background/95 px-4 py-2.5 backdrop-blur">
        <Button variant="ghost" size="icon" onClick={() => navigate('/tasks')} aria-label="Back">
          <ArrowLeft className="size-5" />
        </Button>
        <h1 className="text-lg font-semibold tracking-tight">Planner</h1>
        <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="ml-auto">
          <TabsList>
            <TabsTrigger value="plan">Plan</TabsTrigger>
            <TabsTrigger value="schedule">Schedule</TabsTrigger>
            <TabsTrigger value="team">Team &amp; Calendar</TabsTrigger>
          </TabsList>
        </Tabs>
      </header>

      {error && <div className="px-6 py-3 text-sm text-destructive">{error}</div>}
      {loading && <div className="px-6 py-3 text-sm text-muted-foreground">Loading…</div>}

      {!loading && tab === 'plan' && <div className="p-6"><PlanTree /></div>}
      {!loading && tab === 'schedule' && <ScheduleTab rows={rows} />}
      {!loading && tab === 'team' && <TeamTab people={people} reload={reload} />}
    </div>
  );
}

// ─── Schedule tab: per-person execution view + CSV ───────────────────

function ScheduleTab({ rows }: { rows: ScheduleRow[] }) {
  const parentIds = new Set(rows.map((r) => r.parentId).filter(Boolean) as string[]);
  const scheduled = rows.filter((r) => r.start && !parentIds.has(r.taskId));
  const byPerson = new Map<string, ScheduleRow[]>();
  for (const r of scheduled) {
    const k = r.assigneeName || '— unassigned —';
    if (!byPerson.has(k)) byPerson.set(k, []);
    byPerson.get(k)!.push(r);
  }

  // Full-plan snapshot: the whole tree in order, all fields, + a summary.
  const exportCsv = () => {
    const cell = (v: unknown) => {
      const s = v === null || v === undefined ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const byParent = new Map<string | null, ScheduleRow[]>();
    for (const r of rows) { const k = r.parentId; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k)!.push(r); }
    const titleById = new Map(rows.map((r) => [r.taskId, r.title]));
    const isLeaf = (id: string) => (byParent.get(id) || []).length === 0;
    const fmtDue = (ms: number | null) => (ms ? new Date(ms).toISOString().slice(0, 10) : '');

    const header = ['Level', 'Task', 'Status', 'Assignee', 'Estimate (h)', 'Buffer (h)', 'Priority', 'Blocked By', 'Start', 'End', 'Critical Path', 'Due Date'];
    const lines: string[] = [header.join(',')];
    const walk = (parentId: string | null, level: number) => {
      for (const r of byParent.get(parentId) || []) {
        const blockers = (r.blockedBy || []).map((id) => titleById.get(id) || id).join('; ');
        lines.push([
          level, '  '.repeat(level) + r.title, r.status, r.assigneeName ?? '',
          r.estimateHours ?? '', r.bufferHours ?? '', r.priority || '', blockers,
          r.start, r.end, r.onCriticalPath ? 'yes' : '', fmtDue(r.dueDate),
        ].map(cell).join(','));
        walk(r.taskId, level + 1);
      }
    };
    walk(null, 0);

    const ends = rows.map((r) => r.end).filter(Boolean).sort();
    const totalEffort = rows.filter((r) => isLeaf(r.taskId)).reduce((s, r) => s + (r.estimateHours || 0), 0);
    const today = new Date().toISOString().slice(0, 10);
    lines.push('');
    lines.push([`Snapshot taken ${today}`].map(cell).join(','));
    lines.push(['Project end date', '', '', '', '', '', '', '', '', ends[ends.length - 1] || ''].map(cell).join(','));
    lines.push(['Total effort (h)', '', '', '', totalEffort].map(cell).join(','));

    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `plan-snapshot-${today}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={styles.body}>
      <button className={styles.primary} onClick={exportCsv}>Export plan snapshot (CSV)</button>
      {scheduled.length === 0 && <p className={styles.muted}>Nothing scheduled. Give tasks an estimate + assignee.</p>}
      {[...byPerson.entries()].map(([person, prs]) => {
        const total = prs.reduce((s, r) => s + (r.estimateHours || 0), 0);
        const label = (s: string) => (s === 'CLOSED' ? 'Done' : s === 'IN_PROGRESS' ? 'In progress' : 'To do');
        return (
          <div key={person} className={styles.lane}>
            <h3 className={styles.laneTitle}>{person} <span className={styles.muted}>· {prs.length} task{prs.length !== 1 ? 's' : ''} · {total}h</span></h3>
            {prs.map((r) => (
              <div key={r.taskId} className={`${styles.schedRow} ${r.onCriticalPath ? styles.critical : ''}`}>
                <span className={styles.date}>{r.start} → {r.end}</span>
                <span className={styles.schedTitle}>{r.onCriticalPath ? '★ ' : ''}{r.title}</span>
                <span className={styles.muted}>{r.estimateHours ? `${r.estimateHours}h` : ''}</span>
                <span className={styles.schedStatus}>{label(r.status)}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ─── Team & Calendar tab ─────────────────────────────────────────────

function TeamTab({ people, reload }: { people: Person[]; reload: () => Promise<void> }) {
  const [name, setName] = useState('');
  const [hours, setHours] = useState('8');
  const [weekend, setWeekend] = useState(96);
  const [calId, setCalId] = useState<string>('');
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [holDay, setHolDay] = useState('');
  const [holName, setHolName] = useState('');

  const loadCal = useCallback(async () => {
    const c = await planner.getCalendar();
    setWeekend(c.weekendDays);
    setCalId(c.id);
    setHolidays(await planner.listHolidays(c.id));
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
  useEffect(() => { void loadCal(); }, [loadCal]);

  const addPerson = async () => {
    if (!name.trim()) return;
    await planner.createPerson({ name: name.trim(), hoursPerDay: Number(hours) || 8 });
    setName('');
    await reload();
  };

  const toggleWeekend = async (bit: number) => {
    const next = weekend ^ bit;
    setWeekend(next);
    await planner.upsertCalendar(next);
  };

  const addHoliday = async () => {
    if (!holDay || !calId) return;
    await planner.createHoliday(calId, { day: holDay, name: holName || undefined });
    setHolDay(''); setHolName('');
    setHolidays(await planner.listHolidays(calId));
  };

  return (
    <div className={styles.body}>
      <section className={styles.section}>
        <h3>People</h3>
        <div className={styles.formRow}>
          <input className={styles.txt} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className={styles.numIn} type="number" min="0" value={hours} onChange={(e) => setHours(e.target.value)} title="Hours/day" />
          <button className={styles.primary} onClick={addPerson}>Add person</button>
        </div>
        {people.map((p) => (
          <div key={p.id} className={styles.personRow}>
            <span>{p.name}</span>
            <input
              className={styles.numIn}
              type="number"
              min="0"
              defaultValue={p.hoursPerDay}
              onBlur={async (e) => { await planner.updatePerson(p.id, { hoursPerDay: Number(e.target.value) }); }}
              title="Hours/day"
            />
            <span className={styles.muted}>h/day</span>
            <TimeOffEditor personId={p.id} />
            <button className={styles.danger} onClick={async () => { await planner.deletePerson(p.id); await reload(); }}>Remove</button>
          </div>
        ))}
      </section>

      <section className={styles.section}>
        <h3>Calendar</h3>
        <div className={styles.formRow}>
          <span className={styles.muted}>Weekend / non-working days:</span>
          {WEEKDAYS.map((d) => (
            <label key={d.bit} className={styles.dayChk}>
              <input type="checkbox" checked={(weekend & d.bit) !== 0} onChange={() => toggleWeekend(d.bit)} /> {d.label}
            </label>
          ))}
        </div>
        <div className={styles.formRow}>
          <input className={styles.txt} type="date" value={holDay} onChange={(e) => setHolDay(e.target.value)} />
          <input className={styles.txt} placeholder="Holiday name" value={holName} onChange={(e) => setHolName(e.target.value)} />
          <button className={styles.primary} onClick={addHoliday}>Add holiday</button>
        </div>
        {holidays.map((h) => (
          <div key={h.id} className={styles.personRow}>
            <span>{h.day}</span><span className={styles.muted}>{h.name}</span>
            <button className={styles.danger} onClick={async () => { await planner.deleteHoliday(h.id); setHolidays(await planner.listHolidays(calId)); }}>×</button>
          </div>
        ))}
      </section>
    </div>
  );
}

function TimeOffEditor({ personId }: { personId: string }) {
  const [entries, setEntries] = useState<TimeOffEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [half, setHalf] = useState(false);
  const load = useCallback(async () => { setEntries(await planner.listTimeOff(personId)); }, [personId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
  useEffect(() => { void load(); }, [load]);
  const add = async () => {
    if (!start || !end) return;
    await planner.createTimeOff(personId, { startDay: start, endDay: end, hoursOff: half ? 4 : undefined });
    setStart(''); setEnd(''); setHalf(false); setOpen(false);
    await load();
  };
  const del = async (id: string) => { await planner.deleteTimeOff(id); await load(); };
  return (
    <span className={styles.timeOffWrap}>
      {entries.map((e) => (
        <span key={e.id} className={styles.timeOffChip}>
          {e.startDay}{e.endDay !== e.startDay ? `→${e.endDay}` : ''}{e.hoursOff ? ` ·${e.hoursOff}h` : ''}
          <button className={styles.chipX} onClick={() => del(e.id)} title="Remove">×</button>
        </span>
      ))}
      {open ? (
        <span className={styles.timeOff}>
          <input className={styles.txt} type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          <input className={styles.txt} type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          <label className={styles.muted}><input type="checkbox" checked={half} onChange={(e) => setHalf(e.target.checked)} /> ½</label>
          <button className={styles.primary} onClick={add}>Save</button>
        </span>
      ) : (
        <button className={styles.linkBtn} onClick={() => setOpen(true)}>+ time off</button>
      )}
    </span>
  );
}
