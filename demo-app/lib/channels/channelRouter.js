const localSimulator = require('./localSimulator');
const mailosaurAdapter = require('./mailosaurAdapter');

function modeFor(channel) {
  const envKey = channel === 'email' ? 'EMAIL_CHANNEL_MODE' : 'SMS_CHANNEL_MODE';
  const explicit = process.env[envKey];
  if (explicit) return explicit;
  const hasCreds = channel === 'email'
    ? Boolean(process.env.MAILOSAUR_API_KEY && process.env.MAILOSAUR_EMAIL_SERVER_ID)
    : Boolean(process.env.MAILOSAUR_API_KEY && process.env.MAILOSAUR_SMS_SERVER_ID);
  return hasCreds ? 'mailosaur' : 'simulator';
}

async function deliver(channel, destination, code) {
  const mode = modeFor(channel);
  const body = `Your verification code is ${code}. It expires shortly - do not share it.`;

  if (mode === 'mailosaur') {
    if (channel === 'email') {
      await mailosaurAdapter.sendEmail(destination, 'Your verification code', body);
    } else {
      await mailosaurAdapter.sendSms(destination, body);
    }
    return { mode, destination };
  }

  localSimulator.send(channel, destination, body);
  return { mode, destination };
}

module.exports = { deliver, modeFor };
