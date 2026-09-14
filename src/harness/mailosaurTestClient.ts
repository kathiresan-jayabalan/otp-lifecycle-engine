// Real Mailosaur retrieval used from the test side, independent of the demo
// app's own copy in demo-app/lib/channels/mailosaurAdapter.js. Kept separate
// on purpose: the test client is what an external adopter reusing only the
// Playwright harness against their own SUT would need, without depending on
// this repo's demo app internals.
import MailosaurClient from 'mailosaur';

let client: MailosaurClient | null = null;

function getClient(): MailosaurClient {
  if (!client) {
    if (!process.env.MAILOSAUR_API_KEY) throw new Error('MAILOSAUR_API_KEY is not set');
    client = new MailosaurClient(process.env.MAILOSAUR_API_KEY);
  }
  return client;
}

export function isMailosaurConfigured(): boolean {
  return Boolean(process.env.MAILOSAUR_API_KEY);
}

function extractCode(message: any, digits = 6): string | null {
  const body: string = message?.text?.body || message?.html?.body || '';
  const match = body.match(new RegExp(`\\b(\\d{${digits}})\\b`));
  return match ? match[1] : null;
}

export async function fetchEmailOtp(toAddress: string, digits = 6, timeoutMs = 30000): Promise<string> {
  const serverId = process.env.MAILOSAUR_EMAIL_SERVER_ID;
  if (!serverId) throw new Error('MAILOSAUR_EMAIL_SERVER_ID is not set');
  const message = await getClient().messages.get(serverId, { sentTo: toAddress }, { timeout: timeoutMs });
  const code = extractCode(message, digits);
  if (!code) throw new Error(`could not find a ${digits}-digit code in the Mailosaur message body`);
  return code;
}

export async function fetchSmsOtp(toNumber: string, digits = 6, timeoutMs = 30000): Promise<string> {
  const serverId = process.env.MAILOSAUR_SMS_SERVER_ID;
  if (!serverId) throw new Error('MAILOSAUR_SMS_SERVER_ID is not set');
  const message = await getClient().messages.get(serverId, { sentTo: toNumber }, { timeout: timeoutMs });
  const code = extractCode(message, digits);
  if (!code) throw new Error(`could not find a ${digits}-digit code in the Mailosaur SMS body`);
  return code;
}

export async function deleteAllMessages(serverId: string): Promise<void> {
  await getClient().messages.deleteAll(serverId);
}
