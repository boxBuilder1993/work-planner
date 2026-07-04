import type { ReactNode, ElementType } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FolderKanban, CalendarRange, Users, Search, Settings, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';

const primary = [
  { to: '/', label: 'Projects', icon: FolderKanban },
  { to: '/schedule', label: 'Schedule', icon: CalendarRange },
  { to: '/team', label: 'Team & Calendar', icon: Users },
  { to: '/search', label: 'Search', icon: Search },
];
const secondary = [
  { to: '/knowledge', label: 'Knowledge', icon: BookOpen },
  { to: '/settings', label: 'Settings', icon: Settings },
];

function NavItem({ to, label, icon: Icon, active }: { to: string; label: string; icon: ElementType; active: boolean }) {
  return (
    <Link
      to={to}
      className={cn(
        'flex items-center gap-2.5 rounded-md px-2 py-[7px] text-[13.5px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
        active && 'bg-accent text-foreground',
      )}
    >
      <Icon className="size-4 opacity-70" strokeWidth={2} />
      {label}
    </Link>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const isActive = (to: string) => (to === '/' ? pathname === '/' : pathname.startsWith(to));
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-[236px] flex-none flex-col gap-0.5 border-r bg-muted p-3">
        <div className="flex items-center gap-2 px-2 pb-3 pt-1 text-[15px] font-semibold">
          <span className="size-[18px] rounded-[5px] bg-foreground" />
          WorkPlanner
        </div>
        <nav className="flex flex-col gap-0.5">
          {primary.map((n) => <NavItem key={n.to} {...n} active={isActive(n.to)} />)}
          <div className="mx-1 my-2 h-px bg-border" />
          {secondary.map((n) => <NavItem key={n.to} {...n} active={isActive(n.to)} />)}
        </nav>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
