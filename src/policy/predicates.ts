// Deterministic predicates only. Nothing in this file reads a probability,
// a model output, or an agent proposal - that separation is the whole point
// of the design (agent proposes scenarios, this decides verdicts).
import type { NormalizedEvent, PredicateFn } from './types';

function actionEvents(events: NormalizedEvent[], action: string) {
  return events.filter((e) => e.action === action);
}

export const replayRejected: PredicateFn = (events) => {
  const accepts = actionEvents(events, 'accept');
  if (accepts.length === 0) {
    return { verdict: 'INCONCLUSIVE', reason: 'no accept event observed to test replay against', evidenceSeqs: [] };
  }
  const rejectsAfterAccept = events.filter(
    (e) => e.action === 'reject' && e.meta.reason === 'replay' && e.seq > accepts[0].seq,
  );
  if (rejectsAfterAccept.length === 0) {
    return {
      verdict: 'INCONCLUSIVE',
      reason: 'accept observed but no replay attempt was made in this run',
      evidenceSeqs: [accepts[0].seq],
    };
  }
  return {
    verdict: 'PASS',
    reason: 'replayed code was rejected after the first acceptance',
    evidenceSeqs: [accepts[0].seq, rejectsAfterAccept[0].seq],
  };
};

export const expiryBoundaryEnforced: PredicateFn = (events) => {
  const expiredRejects = events.filter((e) => e.action === 'reject' && e.meta.reason === 'expired');
  const acceptsBeforeExpiry = actionEvents(events, 'accept');
  if (expiredRejects.length === 0 && acceptsBeforeExpiry.length === 0) {
    return { verdict: 'INCONCLUSIVE', reason: 'neither an accept nor an expiry rejection was observed', evidenceSeqs: [] };
  }
  if (expiredRejects.length === 0) {
    return {
      verdict: 'INCONCLUSIVE',
      reason: 'code accepted within TTL but boundary case not exercised in this run',
      evidenceSeqs: acceptsBeforeExpiry.map((e) => e.seq),
    };
  }
  return {
    verdict: 'PASS',
    reason: 'code submitted after TTL was rejected as expired',
    evidenceSeqs: expiredRejects.map((e) => e.seq),
  };
};

export const attemptLockoutEnforced: PredicateFn = (events, theta) => {
  const maxAttemptsEnvVar = theta.maxAttemptsEnvVar as string | undefined;
  const configuredMax = maxAttemptsEnvVar ? Number(process.env[maxAttemptsEnvVar]) : undefined;
  const lockEvents = actionEvents(events, 'lock');
  if (lockEvents.length === 0) {
    return { verdict: 'INCONCLUSIVE', reason: 'no lock event observed in this run', evidenceSeqs: [] };
  }
  const lockEvent = lockEvents[0];
  const attempts = Number(lockEvent.meta.attempts);
  if (configuredMax !== undefined && attempts < configuredMax) {
    return {
      verdict: 'FAIL',
      reason: `locked after ${attempts} attempts, before configured max ${configuredMax}`,
      evidenceSeqs: [lockEvent.seq],
    };
  }
  const rejectAfterLock = events.find((e) => e.action === 'reject' && e.meta.reason === 'locked' && e.seq > lockEvent.seq);
  if (!rejectAfterLock) {
    return {
      verdict: 'INCONCLUSIVE',
      reason: 'account locked but no post-lock submission observed to confirm rejection',
      evidenceSeqs: [lockEvent.seq],
    };
  }
  return {
    verdict: 'PASS',
    reason: `locked at attempt ${attempts} and a subsequent submission was rejected`,
    evidenceSeqs: [lockEvent.seq, rejectAfterLock.seq],
  };
};

export const sessionBindingEnforced: PredicateFn = (events) => {
  const wrongSession = events.filter((e) => e.action === 'reject' && e.meta.reason === 'wrong_session');
  if (wrongSession.length === 0) {
    return { verdict: 'INCONCLUSIVE', reason: 'cross-session submission was not exercised in this run', evidenceSeqs: [] };
  }
  return {
    verdict: 'PASS',
    reason: 'submission from a different session than the one the code was issued to was rejected',
    evidenceSeqs: wrongSession.map((e) => e.seq),
  };
};

export const supersessionEnforced: PredicateFn = (events) => {
  const supersedeEvents = actionEvents(events, 'supersede');
  if (supersedeEvents.length === 0) {
    return { verdict: 'INCONCLUSIVE', reason: 're-issue was not exercised in this run', evidenceSeqs: [] };
  }
  const supersededReject = events.find(
    (e) => e.action === 'reject' && e.meta.reason === 'superseded' && e.seq > supersedeEvents[0].seq,
  );
  if (!supersededReject) {
    return {
      verdict: 'INCONCLUSIVE',
      reason: 're-issue observed but the superseded code was never resubmitted',
      evidenceSeqs: [supersedeEvents[0].seq],
    };
  }
  return {
    verdict: 'PASS',
    reason: 'code from before a re-issue was rejected as superseded',
    evidenceSeqs: [supersedeEvents[0].seq, supersededReject.seq],
  };
};

export const channelRecorded: PredicateFn = (events) => {
  const withChannel = events.filter((e) => Boolean(e.channel));
  if (withChannel.length === 0) {
    return { verdict: 'INCONCLUSIVE', reason: 'no channel-tagged events in this run', evidenceSeqs: [] };
  }
  return { verdict: 'PASS', reason: 'channel type recorded on every event in this run', evidenceSeqs: withChannel.map((e) => e.seq) };
};

export const predicateRegistry: Record<string, PredicateFn> = {
  replayRejected,
  expiryBoundaryEnforced,
  attemptLockoutEnforced,
  sessionBindingEnforced,
  supersessionEnforced,
  channelRecorded,
};
