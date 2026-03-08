import { encrypt, decrypt } from '../crypto/encryption';
import {
  downloadFileByName,
  uploadOrUpdateFile,
  fileExists,
} from '../drive/driveApi';
import {
  DRIVE_FILE_TASKS,
  DRIVE_FILE_COMMENTS,
  DRIVE_FILE_SALT,
} from '../types';
import type { TaskEntity, CommentEntity } from '../types';

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export async function downloadEntityMap<T>(
  token: string,
  fileName: string,
  key: Uint8Array,
): Promise<Record<string, T>> {
  const encryptedBytes = await downloadFileByName(token, fileName);
  if (!encryptedBytes) return {};

  const plainBytes = await decrypt(encryptedBytes, key);
  const json = decoder.decode(plainBytes);
  return JSON.parse(json) as Record<string, T>;
}

export async function uploadEntityMap<T>(
  token: string,
  fileName: string,
  data: Record<string, T>,
  key: Uint8Array,
): Promise<void> {
  const json = JSON.stringify(data);
  const plainBytes = encoder.encode(json);
  const encryptedBytes = await encrypt(plainBytes, key);
  await uploadOrUpdateFile(token, fileName, encryptedBytes);
}

export async function performRestore(
  token: string,
  key: Uint8Array,
): Promise<{
  tasks: Record<string, TaskEntity>;
  comments: Record<string, CommentEntity>;
}> {
  const [tasks, comments] = await Promise.all([
    downloadEntityMap<TaskEntity>(token, DRIVE_FILE_TASKS, key),
    downloadEntityMap<CommentEntity>(token, DRIVE_FILE_COMMENTS, key),
  ]);
  return { tasks, comments };
}

export async function performBackup(
  token: string,
  key: Uint8Array,
  tasks: Record<string, TaskEntity>,
  comments: Record<string, CommentEntity>,
  salt: Uint8Array,
): Promise<void> {
  await Promise.all([
    uploadEntityMap(token, DRIVE_FILE_TASKS, tasks, key),
    uploadEntityMap(token, DRIVE_FILE_COMMENTS, comments, key),
    uploadOrUpdateFile(token, DRIVE_FILE_SALT, salt),
  ]);
}

export async function hasRemoteBackup(token: string): Promise<boolean> {
  return fileExists(token, DRIVE_FILE_TASKS);
}

export async function downloadSalt(
  token: string,
): Promise<Uint8Array | null> {
  const salt = await downloadFileByName(token, DRIVE_FILE_SALT);
  if (salt && salt.length !== 16) {
    throw new Error(
      `Invalid salt: expected 16 bytes but got ${salt.length}. The salt file on Drive may be corrupted.`,
    );
  }
  return salt;
}

export async function uploadSalt(
  token: string,
  salt: Uint8Array,
): Promise<void> {
  await uploadOrUpdateFile(token, DRIVE_FILE_SALT, salt);
}
