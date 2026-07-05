import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Person } from '../api/planner';

// Radix Select forbids an empty-string item value, so "unassigned" uses a sentinel.
const UNASSIGNED = '__unassigned__';

/** Shared assignee dropdown (unassigned + workspace people). */
export default function AssigneeSelect({
  value,
  people,
  onChange,
  className,
}: {
  value: string;
  people: Person[];
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <Select value={value || UNASSIGNED} onValueChange={(v) => onChange(v === UNASSIGNED ? '' : v)}>
      <SelectTrigger className={className ?? 'h-8 w-full text-[13px]'}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={UNASSIGNED}>— unassigned —</SelectItem>
        {people.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
