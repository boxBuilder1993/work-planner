import { useState } from 'react';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Input } from '@/components/ui/input';
import { Plus } from 'lucide-react';

export type PickerOption = { id: string; title: string; context?: string };

/** A searchable task picker (Popover + typeahead) — e.g. for choosing a blocker. */
export default function BlockerPicker({
  options,
  onSelect,
  label = 'add blocker',
}: {
  options: PickerOption[];
  onSelect: (id: string) => void;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');

  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? options.filter((o) => o.title.toLowerCase().includes(needle) || (o.context ?? '').toLowerCase().includes(needle))
    : options;

  const close = () => { setOpen(false); setQ(''); };

  return (
    <Popover open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
      <PopoverTrigger asChild>
        <button className="inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[12px] font-medium hover:bg-muted">
          <Plus className="size-3.5" /> {label}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <div className="border-b p-2">
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tasks…" className="h-8 text-[13px]" />
        </div>
        <div className="max-h-64 overflow-auto p-1">
          {filtered.length === 0 && <div className="px-2 py-3 text-center text-[12.5px] text-muted-foreground">No matching tasks</div>}
          {filtered.slice(0, 50).map((o) => (
            <button
              key={o.id}
              onClick={() => { onSelect(o.id); close(); }}
              className="flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left hover:bg-muted"
            >
              <span className="text-[13px]">{o.title}</span>
              {o.context && <span className="text-[11px] text-muted-foreground">{o.context}</span>}
            </button>
          ))}
          {filtered.length > 50 && <div className="px-2 py-1.5 text-center text-[11px] text-muted-foreground">Refine your search — {filtered.length} matches</div>}
        </div>
      </PopoverContent>
    </Popover>
  );
}
