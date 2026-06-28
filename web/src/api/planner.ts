import { apiFetch, apiPost, apiPatch, apiPut, apiDelete } from './client';

export interface Person {
  id: string;
  name: string;
  email: string | null;
  hoursPerDay: number;
  active: boolean;
}

export interface TimeOffEntry {
  id: string;
  personId: string;
  startDay: string;
  endDay: string;
  hoursOff: number | null;
  note: string | null;
}

export interface CalendarObj {
  id: string;
  weekendDays: number;
}

export interface Holiday {
  id: string;
  day: string;
  name: string | null;
}

export interface Dependency {
  id: string;
  taskId: string;
  dependsOnId: string;
}

export interface ScheduleRow {
  taskId: string;
  title: string;
  parentId: string | null;
  assigneeId: string | null;
  assigneeName: string | null;
  estimateHours: number | null;
  status: string;
  start: string;
  end: string;
  onCriticalPath: boolean;
}

// People + time off
export const listPeople = () => apiFetch<Person[]>('/api/people');
export const createPerson = (b: { name: string; hoursPerDay?: number; email?: string }) =>
  apiPost<Person>('/api/people', b);
export const updatePerson = (id: string, b: Partial<{ name: string; hoursPerDay: number; active: boolean }>) =>
  apiPatch<Person>(`/api/people/${id}`, b);
export const deletePerson = (id: string) => apiDelete(`/api/people/${id}`);
export const listTimeOff = (pid: string) => apiFetch<TimeOffEntry[]>(`/api/people/${pid}/time-off`);
export const createTimeOff = (pid: string, b: { startDay: string; endDay: string; hoursOff?: number; note?: string }) =>
  apiPost<TimeOffEntry>(`/api/people/${pid}/time-off`, b);
export const deleteTimeOff = (id: string) => apiDelete(`/api/time-off/${id}`);

// Calendar + holidays
export const getCalendar = () => apiFetch<CalendarObj>('/api/calendar');
export const upsertCalendar = (weekendDays: number) => apiPut<CalendarObj>('/api/calendar', { weekendDays });
export const listHolidays = (calId: string) => apiFetch<Holiday[]>(`/api/calendar/${calId}/holidays`);
export const createHoliday = (calId: string, b: { day: string; name?: string }) =>
  apiPost<Holiday>(`/api/calendar/${calId}/holidays`, b);
export const deleteHoliday = (id: string) => apiDelete(`/api/holidays/${id}`);

// Dependencies + planner fields + schedule
export const listDependencies = (taskId: string) => apiFetch<Dependency[]>(`/api/tasks/${taskId}/dependencies`);
export const createDependency = (taskId: string, dependsOnId: string) =>
  apiPost<Dependency>(`/api/tasks/${taskId}/dependencies`, { dependsOnId });
export const deleteDependency = (id: string) => apiDelete(`/api/dependencies/${id}`);
export const updateTaskPlanner = (taskId: string, b: Partial<{ assigneeId: string; bufferHours: number }>) =>
  apiPatch(`/api/tasks/${taskId}/planner`, b);
export const getSchedule = (start?: string) =>
  apiFetch<ScheduleRow[]>(`/api/schedule${start ? `?start=${start}` : ''}`);
