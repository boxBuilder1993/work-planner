import { TaskEntity, CommentEntity } from '@types/index';
import { getStoredAuthToken } from './auth';

const API_BASE_URL = process.env.API_URL || 'http://localhost:3000/api';

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

const getAuthHeader = async (): Promise<Record<string, string>> => {
  const token = await getStoredAuthToken();
  return {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };
};

export const fetchTasks = async (): Promise<TaskEntity[]> => {
  try {
    const headers = await getAuthHeader();
    const response = await fetch(`${API_BASE_URL}/tasks`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Failed to fetch tasks:', error);
    throw error;
  }
};

export const createTask = async (task: Partial<TaskEntity>): Promise<TaskEntity> => {
  try {
    const headers = await getAuthHeader();
    const response = await fetch(`${API_BASE_URL}/tasks`, {
      method: 'POST',
      headers,
      body: JSON.stringify(task),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to create task:', error);
    throw error;
  }
};

export const updateTask = async (
  taskId: string,
  updates: Partial<TaskEntity>
): Promise<TaskEntity> => {
  try {
    const headers = await getAuthHeader();
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify(updates),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to update task:', error);
    throw error;
  }
};

export const fetchComments = async (taskId: string): Promise<CommentEntity[]> => {
  try {
    const headers = await getAuthHeader();
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/comments`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to fetch comments:', error);
    throw error;
  }
};

export const createComment = async (
  taskId: string,
  comment: Partial<CommentEntity>
): Promise<CommentEntity> => {
  try {
    const headers = await getAuthHeader();
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/comments`, {
      method: 'POST',
      headers,
      body: JSON.stringify(comment),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to create comment:', error);
    throw error;
  }
};
