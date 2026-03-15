import { useState } from 'react';
import type { TaskEntity, TaskStatus } from '../types';
import { useTasks } from '../hooks/useTasks';
import { toDateInputValue, fromDateInputValue, toDateTimeInputValue, fromDateTimeInputValue } from '../utils';
import ParentPicker from './ParentPicker';
import styles from './TaskForm.module.css';

interface Props {
  task: TaskEntity;
  isNew: boolean;
  onChange: (task: TaskEntity) => void;
  repeatIntervalDays: number | null;
  repeatStartDate: number | null;
  onRepeatIntervalChange: (days: number | null) => void;
  onRepeatStartDateChange: (date: number | null) => void;
}

export default function TaskForm({
  task,
  isNew,
  onChange,
  repeatIntervalDays,
  repeatStartDate,
  onRepeatIntervalChange,
  onRepeatStartDateChange,
}: Props) {
  const { getTaskById } = useTasks();
  const [showParentPicker, setShowParentPicker] = useState(false);

  const parentTask = task.parentId ? getTaskById(task.parentId) : null;

  return (
    <div className={styles.form}>
      <div className={styles.field}>
        <label className={styles.label}>Title</label>
        <input
          className={styles.input}
          type="text"
          value={task.title}
          onChange={(e) => onChange({ ...task, title: e.target.value })}
          placeholder="Task title"
          autoFocus={isNew}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Description</label>
        <textarea
          className={styles.textarea}
          value={task.description}
          onChange={(e) => onChange({ ...task, description: e.target.value })}
          placeholder="Description (optional)"
        />
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label className={styles.label}>Status</label>
          <select
            className={styles.select}
            value={task.status}
            onChange={(e) =>
              onChange({ ...task, status: e.target.value as TaskStatus })
            }
            disabled={isNew}
          >
            <option value="PENDING">Pending</option>
            <option value="CLOSED">Closed</option>
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Priority</label>
          <select
            className={styles.select}
            value={task.priority}
            onChange={(e) =>
              onChange({ ...task, priority: Number(e.target.value) })
            }
          >
            {[1, 2, 3, 4, 5].map((p) => (
              <option key={p} value={p}>
                {p} {p === 1 ? '(Urgent)' : p === 5 ? '(Low)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={styles.dateRow}>
        <div className={styles.field}>
          <label className={styles.label}>Due Date</label>
          <input
            className={styles.input}
            type="date"
            value={toDateInputValue(task.dueDate)}
            onChange={(e) =>
              onChange({
                ...task,
                dueDate: fromDateInputValue(e.target.value),
              })
            }
          />
        </div>
        {task.dueDate !== null && (
          <button
            className={styles.clearButton}
            onClick={() => onChange({ ...task, dueDate: null })}
          >
            Clear
          </button>
        )}
      </div>

      <div className={styles.dateRow}>
        <div className={styles.field}>
          <label className={styles.label}>Planned Time</label>
          <input
            className={styles.input}
            type="datetime-local"
            value={toDateTimeInputValue(task.plannedTime)}
            onChange={(e) =>
              onChange({
                ...task,
                plannedTime: fromDateTimeInputValue(e.target.value),
              })
            }
          />
        </div>
        {task.plannedTime !== null && (
          <button
            className={styles.clearButton}
            onClick={() => onChange({ ...task, plannedTime: null })}
          >
            Clear
          </button>
        )}
      </div>

      <div className={styles.dateRow}>
        <div className={styles.field}>
          <label className={styles.label}>Duration (hours)</label>
          <input
            className={styles.input}
            type="number"
            min="0"
            step="0.25"
            placeholder="Not set"
            value={task.duration ?? ''}
            onChange={(e) => {
              const val = e.target.value;
              onChange({
                ...task,
                duration: val === '' ? null : Math.max(0, Number(val)),
              });
            }}
          />
        </div>
        {task.duration !== null && (
          <button
            className={styles.clearButton}
            onClick={() => onChange({ ...task, duration: null })}
          >
            Clear
          </button>
        )}
      </div>

      <div className={styles.field}>
        <label className={styles.label}>
          <input
            type="checkbox"
            checked={task.aiEnabled}
            onChange={() => onChange({ ...task, aiEnabled: !task.aiEnabled })}
          />{' '}
          AI Enabled
        </label>
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Repeat every (days)</label>
        <div className={styles.dateRow}>
          <input
            className={styles.input}
            type="number"
            min="0"
            placeholder="Off"
            value={repeatIntervalDays ?? ''}
            onChange={(e) => {
              const val = e.target.value;
              onRepeatIntervalChange(val === '' ? null : Math.max(0, Number(val)));
            }}
          />
          {repeatIntervalDays != null && (
            <button
              className={styles.clearButton}
              onClick={() => onRepeatIntervalChange(null)}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {repeatIntervalDays != null && repeatIntervalDays > 0 && (
        <div className={styles.field}>
          <label className={styles.label}>Repeat start date</label>
          <div className={styles.dateRow}>
            <input
              className={styles.input}
              type="date"
              value={repeatStartDate ? toDateInputValue(repeatStartDate) : ''}
              onChange={(e) =>
                onRepeatStartDateChange(fromDateInputValue(e.target.value))
              }
            />
            {repeatStartDate != null && (
              <button
                className={styles.clearButton}
                onClick={() => onRepeatStartDateChange(null)}
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {!isNew && (
        <div className={styles.field}>
          <label className={styles.label}>Parent</label>
          <button
            className={styles.parentButton}
            onClick={() => setShowParentPicker(true)}
          >
            {parentTask ? parentTask.title : 'None (root-level theme)'}
          </button>
        </div>
      )}

      {showParentPicker && !isNew && (
        <ParentPicker
          currentTaskId={task.id}
          currentParentId={task.parentId}
          onSelect={(parentId) => {
            onChange({ ...task, parentId });
            setShowParentPicker(false);
          }}
          onClose={() => setShowParentPicker(false)}
        />
      )}
    </div>
  );
}
