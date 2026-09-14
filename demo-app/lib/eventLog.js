// Normalized event stream the policy engine and Playwright tests read from.
// This is the thing that makes a verdict reproducible - the UI can look right
// while this log shows a replayed code was accepted, so tests assert against
// events, not screenshots.
const clock = require('./clock');

const events = [];
let seq = 0;

function emit(fields) {
  seq += 1;
  const event = {
    seq,
    observerTime: Date.now(),
    sourceTime: clock.now(),
    ...fields,
  };
  events.push(event);
  return event;
}

function since(seqAfter = 0) {
  return events.filter((e) => e.seq > seqAfter);
}

function all() {
  return events.slice();
}

function forSubject(subject) {
  return events.filter((e) => e.subject === subject);
}

function reset() {
  events.length = 0;
  seq = 0;
}

module.exports = { emit, since, all, forSubject, reset };
