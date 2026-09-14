import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import type { NormalizedEvent, PredicateOutcome, Verdict } from '../policy/types';

function sha256(content: string): string {
  return crypto.createHash('sha256').update(content).digest('hex');
}

export interface RunManifest {
  runId: string;
  scenario: string;
  mechanism: string;
  clockMode: 'virtual' | 'wall';
  startedAt: string;
  finishedAt: string;
  result: Verdict;
  files: Record<string, string>;
  bundleSha256: string;
}

// Writes the same three artifacts the design doc describes: events.jsonl,
// verdicts.json, manifest.json. A second process can recompute every hash in
// this file without touching the application under test.
export function sealRun(params: {
  runId: string;
  scenario: string;
  mechanism: string;
  clockMode: 'virtual' | 'wall';
  startedAt: number;
  events: NormalizedEvent[];
  outcomes: PredicateOutcome[];
  overallVerdict: Verdict;
  outDir: string;
}): string {
  const runDir = path.join(params.outDir, params.runId);
  fs.mkdirSync(runDir, { recursive: true });

  const eventsJsonl = params.events.map((e) => JSON.stringify(e)).join('\n');
  const verdictsJson = JSON.stringify(
    { overallVerdict: params.overallVerdict, outcomes: params.outcomes },
    null,
    2,
  );

  fs.writeFileSync(path.join(runDir, 'events.jsonl'), eventsJsonl);
  fs.writeFileSync(path.join(runDir, 'verdicts.json'), verdictsJson);

  const fileHashes: Record<string, string> = {
    'events.jsonl': sha256(eventsJsonl),
    'verdicts.json': sha256(verdictsJson),
  };

  const manifestBody: Omit<RunManifest, 'bundleSha256'> = {
    runId: params.runId,
    scenario: params.scenario,
    mechanism: params.mechanism,
    clockMode: params.clockMode,
    startedAt: new Date(params.startedAt).toISOString(),
    finishedAt: new Date().toISOString(),
    result: params.overallVerdict,
    files: fileHashes,
  };

  const bundleSha256 = sha256(eventsJsonl + verdictsJson + JSON.stringify(manifestBody));
  const manifest: RunManifest = { ...manifestBody, bundleSha256 };

  fs.writeFileSync(path.join(runDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  return runDir;
}
