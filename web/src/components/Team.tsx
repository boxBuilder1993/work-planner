import { useState, useEffect, useCallback } from 'react';
import * as planner from '../api/planner';
import type { Person, TimeOffEntry, Holiday, CalendarObj } from '../api/planner';
import { cn } from '@/lib/utils';
import { ChevronRight, Trash2, Plus } from 'lucide-react';

const DAYS = [
  { label: 'Mon', bit: 1 }, { label: 'Tue', bit: 2 }, { label: 'Wed', bit: 4 },
  { label: 'Thu', bit: 8 }, { label: 'Fri', bit: 16 }, { label: 'Sat', bit: 32 }, { label: 'Sun', bit: 64 },
];

const inputCls = 'h-9 rounded-md border bg-background px-2.5 text-[13px] outline-none focus:border-foreground';
const btnCls = 'inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-[13px] font-medium hover:bg-muted';

export default function Team() {
  const [people, setPeople] = useState<Person[]>([]);
  const [cal, setCal] = useState<CalendarObj | null>(null);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [p, c] = await Promise.all([planner.listPeople(), planner.getCalendar()]);
    const h = await planner.listHolidays(c.id);
    setPeople(p); setCal(c); setHolidays(h); setLoading(false);
  }, []);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
  useEffect(() => { void load(); }, [load]);

  if (loading) return <div className="p-7"><p className="text-sm text-muted-foreground">Loading…</p></div>;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <h1 className="text-[19px] font-semibold tracking-tight">Team &amp; Calendar</h1>
      </header>
      <div className="grid max-w-5xl gap-10 p-7 lg:grid-cols-[1.4fr_1fr]">
        <PeopleSection people={people} onChange={load} />
        <div className="space-y-8">
          {cal && <WeekendSection cal={cal} onChange={load} />}
          {cal && <HolidaySection calId={cal.id} holidays={holidays} onChange={load} />}
        </div>
      </div>
    </div>
  );
}

function PeopleSection({ people, onChange }: { people: Person[]; onChange: () => void }) {
  const [name, setName] = useState('');
  const [hours, setHours] = useState('8');
  const [expanded, setExpanded] = useState<string | null>(null);

  const add = async () => {
    if (!name.trim()) return;
    await planner.createPerson({ name: name.trim(), hoursPerDay: Number(hours) || 8 });
    setName(''); setHours('8'); onChange();
  };

  return (
    <section>
      <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">People</h2>
      <div className="overflow-hidden rounded-xl border">
        {people.length === 0 && <p className="p-4 text-sm text-muted-foreground">No people yet. Add your team below.</p>}
        {people.map((p) => (
          <div key={p.id} className="border-b last:border-b-0">
            <div className="flex items-center gap-3 px-3.5 py-2.5">
              <button onClick={() => setExpanded(expanded === p.id ? null : p.id)} className="text-muted-foreground hover:text-foreground" title="Time off">
                <ChevronRight className={cn('size-4 transition-transform', expanded === p.id && 'rotate-90')} />
              </button>
              <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground">
                {p.name.slice(0, 2).toUpperCase()}
              </span>
              <input
                defaultValue={p.name}
                onBlur={(e) => e.target.value.trim() && e.target.value !== p.name && planner.updatePerson(p.id, { name: e.target.value.trim() }).then(onChange)}
                className={cn(inputCls, 'flex-1 border-transparent bg-transparent px-1 font-medium hover:border-border')}
              />
              <label className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
                <input
                  type="number" min="0" max="24" step="0.5" defaultValue={p.hoursPerDay}
                  onBlur={(e) => Number(e.target.value) !== p.hoursPerDay && planner.updatePerson(p.id, { hoursPerDay: Number(e.target.value) }).then(onChange)}
                  className={cn(inputCls, 'w-16 tabular-nums')}
                /> h/day
              </label>
              <button
                onClick={() => planner.updatePerson(p.id, { active: !p.active }).then(onChange)}
                className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', p.active ? 'text-foreground' : 'text-muted-foreground')}
                title="Toggle active"
              >
                {p.active ? 'Active' : 'Inactive'}
              </button>
              <button onClick={() => planner.deletePerson(p.id).then(onChange)} className="text-muted-foreground hover:text-destructive" title="Remove">
                <Trash2 className="size-4" />
              </button>
            </div>
            {expanded === p.id && <TimeOffPanel personId={p.id} />}
          </div>
        ))}
        <div className="flex items-center gap-2 bg-muted/40 px-3.5 py-2.5">
          <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} placeholder="Add a person…" className={cn(inputCls, 'flex-1')} />
          <input value={hours} onChange={(e) => setHours(e.target.value)} type="number" min="0" max="24" step="0.5" className={cn(inputCls, 'w-16 tabular-nums')} title="Hours per day" />
          <button onClick={add} className={btnCls}><Plus className="size-4" /> Add</button>
        </div>
      </div>
    </section>
  );
}

function TimeOffPanel({ personId }: { personId: string }) {
  const [items, setItems] = useState<TimeOffEntry[]>([]);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [note, setNote] = useState('');

  const load = useCallback(async () => { setItems(await planner.listTimeOff(personId)); }, [personId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
  useEffect(() => { void load(); }, [load]);

  const add = async () => {
    if (!start || !end) return;
    await planner.createTimeOff(personId, { startDay: start, endDay: end, note: note || undefined });
    setStart(''); setEnd(''); setNote(''); load();
  };

  return (
    <div className="space-y-2 border-t bg-muted/30 px-4 py-3 pl-12">
      <div className="text-[11.5px] font-semibold uppercase tracking-wide text-muted-foreground">Time off</div>
      {items.length === 0 && <p className="text-[12.5px] text-muted-foreground">None scheduled.</p>}
      {items.map((t) => (
        <div key={t.id} className="flex items-center gap-2 text-[12.5px]">
          <span className="tabular-nums">{t.startDay} → {t.endDay}</span>
          {t.hoursOff != null && <span className="text-muted-foreground">({t.hoursOff}h/day)</span>}
          {t.note && <span className="text-muted-foreground">· {t.note}</span>}
          <button onClick={() => planner.deleteTimeOff(t.id).then(load)} className="ml-auto text-muted-foreground hover:text-destructive"><Trash2 className="size-3.5" /></button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={cn(inputCls, 'text-[12.5px]')} />
        <span className="text-muted-foreground">→</span>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={cn(inputCls, 'text-[12.5px]')} />
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note (optional)" className={cn(inputCls, 'flex-1 text-[12.5px]')} />
        <button onClick={add} className={btnCls}><Plus className="size-4" /> Add</button>
      </div>
    </div>
  );
}

function WeekendSection({ cal, onChange }: { cal: CalendarObj; onChange: () => void }) {
  const toggle = (bit: number) => planner.upsertCalendar(cal.weekendDays ^ bit).then(onChange);
  return (
    <section>
      <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">Weekend / non-working days</h2>
      <div className="flex gap-1.5">
        {DAYS.map((d) => {
          const off = (cal.weekendDays & d.bit) !== 0;
          return (
            <button key={d.bit} onClick={() => toggle(d.bit)}
              className={cn('flex-1 rounded-md border py-2 text-[12.5px] font-medium', off ? 'bg-foreground text-background' : 'hover:bg-muted')}>
              {d.label}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[12px] text-muted-foreground">Highlighted days are treated as non-working for everyone.</p>
    </section>
  );
}

function HolidaySection({ calId, holidays, onChange }: { calId: string; holidays: Holiday[]; onChange: () => void }) {
  const [day, setDay] = useState('');
  const [name, setName] = useState('');
  const add = async () => {
    if (!day) return;
    await planner.createHoliday(calId, { day, name: name || undefined });
    setDay(''); setName(''); onChange();
  };
  return (
    <section>
      <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-muted-foreground">Company holidays</h2>
      <div className="overflow-hidden rounded-xl border">
        {holidays.length === 0 && <p className="p-3.5 text-[13px] text-muted-foreground">No holidays yet.</p>}
        {holidays.map((h) => (
          <div key={h.id} className="flex items-center gap-2 border-b px-3.5 py-2 text-[13px] last:border-b-0">
            <span className="tabular-nums">{h.day}</span>
            {h.name && <span className="text-muted-foreground">· {h.name}</span>}
            <button onClick={() => planner.deleteHoliday(h.id).then(onChange)} className="ml-auto text-muted-foreground hover:text-destructive"><Trash2 className="size-3.5" /></button>
          </div>
        ))}
        <div className="flex items-center gap-2 bg-muted/40 px-3.5 py-2.5">
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className={cn(inputCls, 'text-[12.5px]')} />
          <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} placeholder="name (optional)" className={cn(inputCls, 'flex-1')} />
          <button onClick={add} className={btnCls}><Plus className="size-4" /> Add</button>
        </div>
      </div>
    </section>
  );
}
