import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import type { TaskEntity } from '../types';

interface TaskCardProps {
  task: TaskEntity;
  onPress?: (task: TaskEntity) => void;
}

export function TaskCard({ task, onPress }: TaskCardProps) {
  return (
    <Pressable 
      style={styles.card}
      onPress={() => onPress?.(task)}
    >
      <View>
        <Text style={styles.title}>{task.title}</Text>
        {task.description && (
          <Text style={styles.description} numberOfLines={2}>
            {task.description}
          </Text>
        )}
        <View style={styles.footer}>
          <View style={[styles.badge, { backgroundColor: getPriorityColor(task.priority) }]}>
            <Text style={styles.badgeText}>Priority {task.priority}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: getStatusColor(task.status) }]}>
            <Text style={styles.badgeText}>{task.status}</Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}

function getPriorityColor(priority: number): string {
  const colors: Record<number, string> = {
    1: '#E53935',
    2: '#F57C00',
    3: '#FDD835',
    4: '#43A047',
    5: '#1E88E5',
  };
  return colors[priority] || '#999';
}

function getStatusColor(status: string): string {
  return status === 'CLOSED' ? '#4CAF50' : '#2196F3';
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#eee',
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  description: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  footer: {
    flexDirection: 'row',
    gap: 8,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  badgeText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '500',
  },
});
