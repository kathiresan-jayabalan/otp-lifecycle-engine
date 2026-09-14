// Real Mailosaur adapter. Both email and SMS go through the same "create
// message" call on the Mailosaur SDK - the server picks email vs SMS delivery
// based on which server ID and address format you pass. Field names here are
// from the mailosaur Node SDK docs at the time this was written; check them
// against your installed SDK version if the send call rejects.
const MailosaurClient = require('mailosaur');

let client = null;

function getClient() {
  if (!client) {
    if (!process.env.MAILOSAUR_API_KEY) {
      throw new Error('MAILOSAUR_API_KEY is not set');
    }
    client = new MailosaurClient(process.env.MAILOSAUR_API_KEY);
  }
  return client;
}

async function sendEmail(toAddress, subject, textBody) {
  const serverId = process.env.MAILOSAUR_EMAIL_SERVER_ID;
  if (!serverId) throw new Error('MAILOSAUR_EMAIL_SERVER_ID is not set');
  return getClient().messages.create(serverId, {
    to: toAddress,
    send: true,
    subject,
    text: textBody,
  });
}

async function sendSms(toNumber, textBody) {
  const serverId = process.env.MAILOSAUR_SMS_SERVER_ID;
  if (!serverId) throw new Error('MAILOSAUR_SMS_SERVER_ID is not set');
  return getClient().messages.create(serverId, {
    to: toNumber,
    send: true,
    text: textBody,
  });
}

// Retrieval side, used by the Playwright fixtures rather than by the demo
// app itself - the app only sends. messages.get() long-polls the Mailosaur
// search endpoint until a match shows up or the timeout elapses, same
// behaviour as the cypress-mailosaur mailosaurGetMessage command it mirrors.
async function receiveEmail(toAddress, timeoutMs = 30000) {
  const serverId = process.env.MAILOSAUR_EMAIL_SERVER_ID;
  if (!serverId) throw new Error('MAILOSAUR_EMAIL_SERVER_ID is not set');
  return getClient().messages.get(serverId, { sentTo: toAddress }, { timeout: timeoutMs });
}

async function receiveSms(toNumber, timeoutMs = 30000) {
  const serverId = process.env.MAILOSAUR_SMS_SERVER_ID;
  if (!serverId) throw new Error('MAILOSAUR_SMS_SERVER_ID is not set');
  return getClient().messages.get(serverId, { sentTo: toNumber }, { timeout: timeoutMs });
}

function extractCode(message, digits = 6) {
  const body = message?.text?.body || message?.html?.body || '';
  const match = body.match(new RegExp(`\\b(\\d{${digits}})\\b`));
  return match ? match[1] : null;
}

module.exports = { sendEmail, sendSms, receiveEmail, receiveSms, extractCode, getClient };
