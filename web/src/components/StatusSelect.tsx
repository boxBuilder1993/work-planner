import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

/** Shared task-status dropdown (To do / In progress / Done). */
export default function StatusSelect({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={className ?? 'h-8 w-[132px] text-[13px]'}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value="PENDING">To do</SelectItem>
        <SelectItem value="IN_PROGRESS">In progress</SelectItem>
        <SelectItem value="CLOSED">Done</SelectItem>
      </SelectContent>
    </Select>
  );
}
