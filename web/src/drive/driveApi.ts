const DRIVE_API = 'https://www.googleapis.com/drive/v3';
const UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3';

export class UnauthorizedError extends Error {
  constructor() {
    super('Unauthorized: access token expired or revoked');
    this.name = 'UnauthorizedError';
  }
}

async function driveRequest(
  url: string,
  token: string,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    throw new UnauthorizedError();
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Drive API error ${res.status}: ${text}`);
  }
  return res;
}

export async function findFileId(
  token: string,
  fileName: string,
): Promise<string | null> {
  const query = encodeURIComponent(
    `name='${fileName}' and 'appDataFolder' in parents and trashed=false`,
  );
  const res = await driveRequest(
    `${DRIVE_API}/files?spaces=appDataFolder&q=${query}&fields=files(id)`,
    token,
  );
  const data = await res.json();
  return data.files?.[0]?.id ?? null;
}

export async function downloadFile(
  token: string,
  fileId: string,
): Promise<Uint8Array> {
  const res = await driveRequest(
    `${DRIVE_API}/files/${fileId}?alt=media`,
    token,
  );
  const buffer = await res.arrayBuffer();
  return new Uint8Array(buffer);
}

export async function uploadFile(
  token: string,
  fileName: string,
  data: Uint8Array,
  existingFileId?: string,
): Promise<void> {
  if (existingFileId) {
    // Update existing file
    const boundary = '---workplanner-boundary---';
    const metadata = JSON.stringify({});
    const body = buildMultipartBody(boundary, metadata, data);
    await driveRequest(
      `${UPLOAD_API}/files/${existingFileId}?uploadType=multipart`,
      token,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body,
      },
    );
  } else {
    // Create new file
    const boundary = '---workplanner-boundary---';
    const metadata = JSON.stringify({
      name: fileName,
      parents: ['appDataFolder'],
    });
    const body = buildMultipartBody(boundary, metadata, data);
    await driveRequest(
      `${UPLOAD_API}/files?uploadType=multipart`,
      token,
      {
        method: 'POST',
        headers: {
          'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body,
      },
    );
  }
}

function buildMultipartBody(
  boundary: string,
  metadata: string,
  data: Uint8Array,
): Blob {
  const encoder = new TextEncoder();
  const parts: BlobPart[] = [
    encoder.encode(
      `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${metadata}\r\n`,
    ) as BlobPart,
    encoder.encode(
      `--${boundary}\r\nContent-Type: application/octet-stream\r\n\r\n`,
    ) as BlobPart,
    data as BlobPart,
    encoder.encode(`\r\n--${boundary}--`) as BlobPart,
  ];
  return new Blob(parts);
}

export async function deleteFile(
  token: string,
  fileId: string,
): Promise<void> {
  await driveRequest(`${DRIVE_API}/files/${fileId}`, token, {
    method: 'DELETE',
  });
}

export async function fileExists(
  token: string,
  fileName: string,
): Promise<boolean> {
  const id = await findFileId(token, fileName);
  return id !== null;
}

export async function downloadFileByName(
  token: string,
  fileName: string,
): Promise<Uint8Array | null> {
  const fileId = await findFileId(token, fileName);
  if (!fileId) return null;
  return downloadFile(token, fileId);
}

export async function uploadOrUpdateFile(
  token: string,
  fileName: string,
  data: Uint8Array,
): Promise<void> {
  const existingId = await findFileId(token, fileName);
  await uploadFile(token, fileName, data, existingId ?? undefined);
}
