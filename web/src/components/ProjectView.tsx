import { useState, useEffect, Fragment } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import ScheduleGrid from './ScheduleGrid';
import TaskPlan from './TaskPlan';
import { getBreadcrumbs } from '../api/tasks';
import type { TaskEntity } from '../types';

// Clean underline tab (no box): neutralize shadcn's default active fill/border/
// rounding and use only a bottom border as the selected indicator.
const tabCls =
  'flex-none rounded-none border-x-0 border-t-0 border-b-2 border-transparent bg-transparent px-2 py-3 text-[14px] font-medium text-muted-foreground shadow-none transition-colors hover:text-foreground ' +
  'data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none ' +
  'dark:data-[state=active]:border-foreground dark:data-[state=active]:bg-transparent';

export default function ProjectView() {
  const { taskId } = useParams<{ taskId: string }>();
  const [trail, setTrail] = useState<TaskEntity[]>([]);

  useEffect(() => {
    if (!taskId) return;
    getBreadcrumbs(taskId).then(setTrail).catch(() => setTrail([]));
  }, [taskId]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <div className="flex flex-wrap items-center text-[13.5px] text-muted-foreground">
          <Link to="/" className="hover:text-foreground">Projects</Link>
          {trail.map((t, i) => (
            <Fragment key={t.id}>
              <span className="mx-1.5">/</span>
              {i === trail.length - 1 ? (
                <span className="font-semibold text-foreground">{t.title}</span>
              ) : (
                <Link to={`/projects/${t.id}`} className="hover:text-foreground">{t.title}</Link>
              )}
            </Fragment>
          ))}
          {trail.length === 0 && <><span className="mx-1.5">/</span><span className="text-foreground">…</span></>}
        </div>
      </header>
      <Tabs defaultValue="plan" className="flex flex-1 flex-col gap-0">
        <div className="border-b px-7">
          <TabsList className="h-auto rounded-none border-0 bg-transparent p-0">
            <TabsTrigger value="plan" className={tabCls}>Plan</TabsTrigger>
            <TabsTrigger value="schedule" className={tabCls}>Schedule</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="plan" className="p-7 pt-5 duration-200 animate-in fade-in-0 slide-in-from-bottom-1">
          {taskId && <TaskPlan taskId={taskId} />}
        </TabsContent>
        <TabsContent value="schedule" className="p-7 pt-5 duration-200 animate-in fade-in-0 slide-in-from-bottom-1">
          {taskId && <ScheduleGrid rootId={taskId} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}
