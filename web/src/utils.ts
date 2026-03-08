const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

export function formatDate(millis: number): string {
  return dateFormatter.format(new Date(millis));
}

export function isOverdue(dueDateMillis: number): boolean {
  const now = new Date();
  const dueDate = new Date(dueDateMillis);
  // Compare date only (strip time)
  now.setHours(0, 0, 0, 0);
  dueDate.setHours(0, 0, 0, 0);
  return dueDate < now;
}

export function toDateInputValue(millis: number | null): string {
  if (millis === null) return '';
  const d = new Date(millis);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function fromDateInputValue(value: string): number | null {
  if (!value) return null;
  const d = new Date(value + 'T00:00:00');
  return d.getTime();
}

export function toDateTimeInputValue(millis: number | null): string {
  if (millis === null) return '';
  const d = new Date(millis);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

export function fromDateTimeInputValue(value: string): number | null {
  if (!value) return null;
  const d = new Date(value);
  return d.getTime();
}

export function formatDateTime(millis: number): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(millis));
}
