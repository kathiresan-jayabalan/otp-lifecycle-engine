import { expect, request as newRequestContext } from '@playwright/test';
import { Given, When, Then, finalizeEvidence } from '../support/fixtures';

Given('a fresh account with a matching email and phone', async ({ request, state }) => {
  const res = await request.post('/signup', {
    form: { email: state.email, phone: state.phone },
  });
  expect(res.status()).toBeLessThan(400);
});

When('I request an {word} verification code', async ({ request, demoApp, state }, channel: string) => {
  const res = await request.post('/login/otp/start', {
    form: { email: state.email, channel },
  });
  expect(res.status()).toBeLessThan(400);

  const destination = channel === 'sms' ? state.phone : state.email;
  const message = await demoApp.simulatorInboxFor(destination);
  expect(message, `no ${channel} message found in the local simulator inbox for ${destination}`).not.toBeNull();

  const codeMatch = message!.body.match(/\b(\d{6})\b/);
  expect(codeMatch, 'six-digit code not found in message body').not.toBeNull();
  state.lastCode = codeMatch![1];
  state.lastSubmitBody = { subjectId: state.subjectId, channel };
});

When('I submit the received code', async ({ request, state }) => {
  const res = await request.post('/otp/verify', {
    form: { ...state.lastSubmitBody, code: state.lastCode },
  });
  expect(res.status()).toBeLessThan(400);
});

When('I submit the same code again', async ({ request, state }) => {
  await request.post('/otp/verify', {
    form: { ...state.lastSubmitBody, code: state.lastCode },
  });
});

Then('the login should succeed', async ({ request }) => {
  const res = await request.get('/dashboard');
  expect(res.status()).toBe(200);
});

Then('the submission should be rejected with reason {string}', async ({ request, state }, reason: string) => {
  const res = await request.post('/otp/verify', {
    form: { ...state.lastSubmitBody, code: state.lastCode },
  });
  const body = await res.json();
  expect(body.reason).toBe(reason);
});

When('the server clock advances past the code\'s expiry', async ({ demoApp }) => {
  const ttlSeconds = Number(process.env.OTP_TTL_SECONDS || 120);
  await demoApp.advanceClock((ttlSeconds + 5) * 1000);
});

When('I submit an incorrect code repeatedly until locked', async ({ request, state }) => {
  const maxAttempts = Number(process.env.OTP_MAX_ATTEMPTS || 5);
  const wrongCode = state.lastCode === '000000' ? '111111' : '000000';
  for (let i = 0; i < maxAttempts; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await request.post('/otp/verify', { form: { ...state.lastSubmitBody, code: wrongCode } });
  }
});

Then('the account should be locked', async ({ request, state }) => {
  const res = await request.post('/otp/verify', {
    form: { ...state.lastSubmitBody, code: state.lastCode },
  });
  const body = await res.json();
  expect(body.reason).toBe('locked');
});

When('a second browser session submits the same code', async ({ baseURL, state }) => {
  const secondSession = await newRequestContext.newContext({ baseURL });
  const res = await secondSession.post('/otp/verify', {
    form: { ...state.lastSubmitBody, code: state.lastCode },
  });
  const body = await res.json();
  state.secondSessionResult = { status: res.status(), outcome: body.outcome, reason: body.reason };
  await secondSession.dispose();
});

Then('the second session\'s submission should be rejected with reason {string}', async ({ state }, reason: string) => {
  expect(state.secondSessionResult?.reason).toBe(reason);
});

When('I request a new {word} verification code before using the first', async ({ request, demoApp, state }, channel: string) => {
  state.previousCode = state.lastCode;
  await request.post('/login/otp/start', { form: { email: state.email, channel } });

  const destination = channel === 'sms' ? state.phone : state.email;
  const message = await demoApp.simulatorInboxFor(destination);
  const codeMatch = message!.body.match(/\b(\d{6})\b/);
  state.lastCode = codeMatch![1];
  state.lastSubmitBody = { subjectId: state.subjectId, channel };
});

Then('the first code should be rejected as superseded', async ({ request, state }) => {
  const res = await request.post('/otp/verify', {
    form: { ...state.lastSubmitBody, code: state.previousCode },
  });
  const body = await res.json();
  expect(body.reason).toBe('superseded');
});

Then('the control profile verdict for {string} should be {string}', async ({ demoApp, state }, controlId: string, expected: string) => {
  const lastChannel = (state.lastSubmitBody as { channel?: string } | null)?.channel;
  const mechanism = controlId.startsWith('passkey')
    ? 'passkey'
    : lastChannel === 'sms' ? 'sms-otp' : 'email-otp';
  const { outcomes } = await finalizeEvidence(demoApp, state, controlId, mechanism);
  const outcome = outcomes.find((o) => o.controlId === controlId);
  expect(outcome, `no evaluated outcome for control ${controlId}`).toBeDefined();
  expect(outcome!.verdict, outcome!.reason).toBe(expected);
});
