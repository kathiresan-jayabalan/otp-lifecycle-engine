import crypto from 'crypto';
import path from 'path';
import type { APIRequestContext } from '@playwright/test';
import { test as base, createBdd } from 'playwright-bdd';
import { DemoAppClient } from '../src/harness/demoAppClient';
import { loadProfiles, evaluate } from '../src/policy/engine';
import { sealRun } from '../src/evidence/seal';
import type { NormalizedEvent, PredicateOutcome, Verdict } from '../src/policy/types';

export interface ScenarioState {
  subjectId: string;
  email: string;
  phone: string;
  lastCode: string | null;
  lastSubmitBody: Record<string, unknown> | null;
  previousCode?: string | null;
  secondSessionResult?: { status: number; outcome?: string; reason?: string };
  secondSession?: APIRequestContext;
  verdicts?: Record<string, PredicateOutcome>;
  startedAt: number;
}

type Fixtures = {
  demoApp: DemoAppClient;
  state: ScenarioState;
};

export const test = base.extend<Fixtures>({
  demoApp: async ({ baseURL }, use) => {
    await use(new DemoAppClient(baseURL || 'http://localhost:4000'));
  },

  // eslint-disable-next-line no-empty-pattern
  state: async ({}, use) => {
    // userStore keys every user by email.toLowerCase() (see demo-app/lib/userStore.js
    // upsert()) - subjectId here must match that exactly, not an independent id,
    // or /internal/events?subject= will never find anything for this scenario.
    const email = `subj-${crypto.randomUUID()}@example.test`;
    const state: ScenarioState = {
      subjectId: email,
      email,
      phone: `+1555${String(Math.floor(1000000 + Math.random() * 9000000))}`,
      lastCode: null,
      lastSubmitBody: null,
      startedAt: Date.now(),
    };
    await use(state);
  },
});

export const { Given, When, Then, Before, After } = createBdd(test);

// The demo app's clock is a single process-wide offset (see demo-app/lib/clock.js).
// Scenarios run serially against the same process, so an expiry scenario that
// advances the clock would otherwise leak into whatever scenario runs next.
Before(async ({ demoApp }) => {
  await demoApp.resetClock();
});

const OTP_PROFILE_PATH = path.join('control-profiles', 'otp-controls.yaml');
const EVIDENCE_DIR = path.join(process.cwd(), 'evidence-runs');

export async function finalizeEvidence(
  demoApp: DemoAppClient,
  state: ScenarioState,
  scenarioName: string,
  mechanism: 'email-otp' | 'sms-otp',
): Promise<{ outcomes: PredicateOutcome[]; overallVerdict: Verdict }> {
  const events: NormalizedEvent[] = (await demoApp.eventsForSubject(state.subjectId)) as NormalizedEvent[];
  const profile = loadProfiles(OTP_PROFILE_PATH);

  const { outcomes, overallVerdict } = evaluate(profile, events);

  state.verdicts = Object.fromEntries(outcomes.map((o) => [o.controlId, o]));

  sealRun({
    runId: `${state.subjectId}-${Date.now()}`,
    scenario: scenarioName,
    mechanism,
    clockMode: 'virtual',
    startedAt: state.startedAt,
    events,
    outcomes,
    overallVerdict,
    outDir: EVIDENCE_DIR,
  });

  return { outcomes, overallVerdict };
}
