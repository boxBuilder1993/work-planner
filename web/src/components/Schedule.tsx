import ScheduleGrid from './ScheduleGrid';

export default function Schedule() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <h1 className="text-[19px] font-semibold tracking-tight">Schedule</h1>
      </header>
      <div className="p-7">
        <ScheduleGrid />
      </div>
    </div>
  );
}
