const PBKDF2_ITERATIONS = 210_000;
const KEY_LENGTH_BITS = 256;
const SALT_LENGTH_BYTES = 16;
const IV_LENGTH_BYTES = 12;
const TAG_LENGTH_BITS = 128;

export function generateSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(SALT_LENGTH_BYTES));
}

export async function deriveKey(
  passphrase: string,
  salt: Uint8Array,
): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(passphrase),
    'PBKDF2',
    false,
    ['deriveBits'],
  );

  const derivedBits = await crypto.subtle.deriveBits(
    {
      name: 'PBKDF2',
      salt: salt.buffer as ArrayBuffer,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    keyMaterial,
    KEY_LENGTH_BITS,
  );

  return new Uint8Array(derivedBits);
}

export async function encrypt(
  plainBytes: Uint8Array,
  keyBytes: Uint8Array,
): Promise<Uint8Array> {
  const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH_BYTES));

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyBytes.buffer as ArrayBuffer,
    'AES-GCM',
    false,
    ['encrypt'],
  );

  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, tagLength: TAG_LENGTH_BITS },
    cryptoKey,
    plainBytes.buffer as ArrayBuffer,
  );

  // Prepend IV to ciphertext (which includes the auth tag)
  const result = new Uint8Array(IV_LENGTH_BYTES + ciphertext.byteLength);
  result.set(iv, 0);
  result.set(new Uint8Array(ciphertext), IV_LENGTH_BYTES);
  return result;
}

export async function decrypt(
  encryptedBytes: Uint8Array,
  keyBytes: Uint8Array,
): Promise<Uint8Array> {
  const iv = encryptedBytes.slice(0, IV_LENGTH_BYTES);
  const ciphertext = encryptedBytes.slice(IV_LENGTH_BYTES);

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyBytes.buffer as ArrayBuffer,
    'AES-GCM',
    false,
    ['decrypt'],
  );

  const plainBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv, tagLength: TAG_LENGTH_BITS },
    cryptoKey,
    ciphertext.buffer as ArrayBuffer,
  );

  return new Uint8Array(plainBuffer);
}
