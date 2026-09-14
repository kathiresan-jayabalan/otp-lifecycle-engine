// Talks to the demo app's /internal/* introspection routes. These routes are
// only mounted when NODE_ENV !== 'production' (see demo-app/server.js) - the
// harness has no other way to read the event stream or move the clock.
import type { NormalizedEvent } from '../policy/types';

export class DemoAppClient {
  constructor(private readonly baseURL: string) {}

  async resetState(): Promise<void> {
    await fetch(`${this.baseURL}/internal/reset`, { method: 'POST' });
  }

  async advanceClock(ms: number): Promise<number> {
    const res = await fetch(`${this.baseURL}/internal/clock/advance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ms }),
    });
    const body = await res.json();
    return body.offsetMs;
  }

  async resetClock(): Promise<void> {
    await fetch(`${this.baseURL}/internal/clock/reset`, { method: 'POST' });
  }

  async eventsForSubject(subject: string): Promise<NormalizedEvent[]> {
    const res = await fetch(`${this.baseURL}/internal/events?subject=${encodeURIComponent(subject)}`);
    return res.json();
  }

  async simulatorInboxFor(destination: string): Promise<{ channel: string; to: string; body: string; sentAt: number } | null> {
    const res = await fetch(`${this.baseURL}/internal/simulator/inbox?to=${encodeURIComponent(destination)}`);
    const body = await res.json();
    return body || null;
  }
}
