// Local channel adapter: keeps sent messages in memory and exposes them
// through /internal/simulator/inbox. This is the "SMS simulator" component
// from the design doc - it exists so the whole demo runs with zero external
// accounts. Swap SMS_CHANNEL_MODE=mailosaur / EMAIL_CHANNEL_MODE=mailosaur to
// use the real adapter once Mailosaur credentials are set.
const inbox = [];

function send(channel, to, body) {
  const message = { channel, to, body, sentAt: Date.now() };
  inbox.push(message);
  return message;
}

function latestFor(to) {
  for (let i = inbox.length - 1; i >= 0; i -= 1) {
    if (inbox[i].to === to) return inbox[i];
  }
  return null;
}

function reset() {
  inbox.length = 0;
}

module.exports = { send, latestFor, reset, all: () => inbox.slice() };
