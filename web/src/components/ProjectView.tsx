import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import PlanTree from './PlanTree';
import { getTask } from '../api/tasks';
import type { TaskEntity } from '../types';

export default function ProjectView() {
  const { taskId } = useParams<{ taskId: string }>();
  const [task, setTask] = useState<TaskEntity | null>(null);

  useEffect(() => {
    if (!taskId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load on mount
    getTask(taskId).then(setTask).catch(() => {});
  }, [taskId]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <div className="text-[13.5px] text-muted-foreground">
          <Link to="/" className="hover:text-foreground">Projects</Link>
          <span className="mx-1.5">/</span>
          <span className="font-semibold text-foreground">{task?.title ?? '…'}</span>
        </div>
      </header>
      <Tabs defaultValue="plan" className="flex flex-1 flex-col gap-0">
        <div className="border-b px-7">
          <TabsList className="h-auto rounded-none border-0 bg-transparent p-0">
            <TabsTrigger value="plan" className="rounded-none border-b-2 border-transparent px-3 py-3 data-[state=active]:border-foreground data-[state=active]:shadow-none">Plan</TabsTrigger>
            <TabsTrigger value="schedule" className="rounded-none border-b-2 border-transparent px-3 py-3 data-[state=active]:border-foreground data-[state=active]:shadow-none">Schedule</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="plan" className="p-7 pt-5">
          {taskId && <PlanTree rootId={taskId} />}
        </TabsContent>
        <TabsContent value="schedule" className="p-7 pt-5">
          <p className="text-sm text-muted-foreground">Schedule grid for this project — coming next.</p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
