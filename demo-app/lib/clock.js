// Injectable clock so the test harness can cross OTP expiry boundaries without
// sleeping in real time. Production code should never call advance()/reset() -
// server.js only wires the /internal/clock route outside NODE_ENV=production.
let offsetMs = 0;

function now() {
  return Date.now() + offsetMs;
}

function advance(ms) {
  offsetMs += ms;
  return offsetMs;
}

function reset() {
  offsetMs = 0;
}

module.exports = { now, advance, reset };
