// In-memory user records only. This is a demo SUT, not a real identity
// store - no password hashing library, no persistence, restart wipes state.
const users = new Map();
const credentials = new Map(); // subjectId -> array of passkey credential records

function upsert(email, phone) {
  const subjectId = email.toLowerCase();
  if (!users.has(subjectId)) {
    users.set(subjectId, {
      subjectId,
      email,
      phone,
      createdAt: Date.now(),
      locked: false,
      lockedUntil: null,
    });
  }
  return users.get(subjectId);
}

function find(email) {
  return users.get((email || '').toLowerCase());
}

function lock(subjectId, untilMs) {
  const user = users.get(subjectId);
  if (!user) return;
  user.locked = true;
  user.lockedUntil = untilMs;
}

function unlockIfExpired(subjectId, nowMs) {
  const user = users.get(subjectId);
  if (user && user.locked && user.lockedUntil !== null && nowMs >= user.lockedUntil) {
    user.locked = false;
    user.lockedUntil = null;
  }
}

function addCredential(subjectId, record) {
  const list = credentials.get(subjectId) || [];
  list.push(record);
  credentials.set(subjectId, list);
}

function getCredentials(subjectId) {
  return credentials.get(subjectId) || [];
}

function revokeCredential(subjectId, credentialId) {
  const list = credentials.get(subjectId) || [];
  const target = list.find((c) => c.credentialId === credentialId);
  if (target) target.revoked = true;
  return target;
}

function reset() {
  users.clear();
  credentials.clear();
}

module.exports = {
  upsert,
  find,
  lock,
  unlockIfExpired,
  addCredential,
  getCredentials,
  revokeCredential,
  reset,
};
