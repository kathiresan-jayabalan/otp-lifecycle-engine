// OTP lifecycle state machine: issued -> valid -> consumed | expired | locked.
// One active token per (subject, channel) pair. Re-issuing supersedes the
// previous token instead of letting two valid codes exist at once.
const crypto = require('crypto');
const clock = require('./clock');
const eventLog = require('./eventLog');

const OTP_LENGTH = Number(process.env.OTP_LENGTH || 6);
const TTL_MS = Number(process.env.OTP_TTL_SECONDS || 120) * 1000;
const MAX_ATTEMPTS = Number(process.env.OTP_MAX_ATTEMPTS || 5);
const LOCKOUT_MS = Number(process.env.OTP_LOCKOUT_SECONDS || 300) * 1000;

// tokens: subjectId -> channel -> { current: record|null, supersededCodes: Set<string> }
// supersededCodes lives on the bucket, not the record, because issuing a new
// code replaces `current` entirely - without this, a superseded code could
// never be told apart from one that was simply never issued.
const tokens = new Map();

function generateCode() {
  const max = 10 ** OTP_LENGTH;
  const value = crypto.randomInt(0, max);
  return String(value).padStart(OTP_LENGTH, '0');
}

function bucketFor(subjectId, channel) {
  if (!tokens.has(subjectId)) tokens.set(subjectId, new Map());
  const subjectChannels = tokens.get(subjectId);
  if (!subjectChannels.has(channel)) {
    subjectChannels.set(channel, { current: null, supersededCodes: new Set() });
  }
  return subjectChannels.get(channel);
}

function issue(subjectId, channel, sessionId) {
  const bucket = bucketFor(subjectId, channel);
  if (bucket.current && bucket.current.status === 'issued') {
    bucket.current.status = 'superseded';
    bucket.supersededCodes.add(bucket.current.code);
    eventLog.emit({
      subject: subjectId,
      session: sessionId,
      mechanism: `${channel}-otp`,
      action: 'supersede',
      channel,
      meta: { supersededCode: bucket.current.code },
    });
  }

  const code = generateCode();
  const record = {
    code,
    sessionId,
    issuedAt: clock.now(),
    expiresAt: clock.now() + TTL_MS,
    attempts: 0,
    status: 'issued',
    consumedCodes: new Set(),
  };
  bucket.current = record;

  eventLog.emit({
    subject: subjectId,
    session: sessionId,
    mechanism: `${channel}-otp`,
    action: 'issue',
    channel,
    meta: { ttlMs: TTL_MS, expiresAt: record.expiresAt },
  });

  return { code, expiresAt: record.expiresAt };
}

// deliver() is a separate step from issue() so tests can assert delivery as
// its own event, matching the paper's "issue" vs "deliver" distinction. The
// channel adapter (email/sms) calls this after the message actually goes out.
function markDelivered(subjectId, channel, sessionId, providerMeta) {
  eventLog.emit({
    subject: subjectId,
    session: sessionId,
    mechanism: `${channel}-otp`,
    action: 'deliver',
    channel,
    meta: providerMeta || {},
  });
}

function verify(subjectId, channel, sessionId, submittedCode) {
  const bucket = bucketFor(subjectId, channel);
  const record = bucket.current;
  const base = { subject: subjectId, session: sessionId, mechanism: `${channel}-otp`, channel };

  if (bucket.supersededCodes.has(submittedCode)) {
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'superseded' } });
    return { outcome: 'reject', reason: 'superseded' };
  }

  if (!record) {
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'no_active_token' } });
    return { outcome: 'reject', reason: 'no_active_token' };
  }

  if (record.status === 'locked') {
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'locked' } });
    return { outcome: 'reject', reason: 'locked' };
  }

  if (record.sessionId !== sessionId) {
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'wrong_session' } });
    return { outcome: 'reject', reason: 'wrong_session' };
  }

  if (record.consumedCodes.has(submittedCode)) {
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'replay' } });
    return { outcome: 'reject', reason: 'replay' };
  }

  if (clock.now() >= record.expiresAt) {
    record.status = 'expired';
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'expired' } });
    return { outcome: 'reject', reason: 'expired' };
  }

  if (submittedCode !== record.code) {
    record.attempts += 1;
    if (record.attempts >= MAX_ATTEMPTS) {
      record.status = 'locked';
      record.lockedUntil = clock.now() + LOCKOUT_MS;
      eventLog.emit({ ...base, action: 'lock', meta: { attempts: record.attempts } });
    }
    eventLog.emit({ ...base, action: 'reject', meta: { reason: 'invalid_code', attempts: record.attempts } });
    return { outcome: 'reject', reason: 'invalid_code', attempts: record.attempts };
  }

  record.status = 'consumed';
  record.consumedCodes.add(submittedCode);
  eventLog.emit({ ...base, action: 'accept', meta: {} });
  return { outcome: 'accept' };
}

function status(subjectId, channel) {
  const bucket = bucketFor(subjectId, channel);
  if (!bucket.current) return null;
  return {
    status: bucket.current.status,
    expiresAt: bucket.current.expiresAt,
    attempts: bucket.current.attempts,
  };
}

function reset() {
  tokens.clear();
}

module.exports = { issue, markDelivered, verify, status, reset, TTL_MS, MAX_ATTEMPTS, LOCKOUT_MS };
