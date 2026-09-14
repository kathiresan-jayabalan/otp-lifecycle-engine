import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import { predicateRegistry } from './predicates';
import type { ControlProfile, NormalizedEvent, PredicateOutcome, Verdict } from './types';

export function loadProfile(profilePath: string): ControlProfile {
  const raw = fs.readFileSync(profilePath, 'utf8');
  return yaml.load(raw) as ControlProfile;
}

function requiredEvidencePresent(events: NormalizedEvent[], fields: string[]): boolean {
  if (events.length === 0) return false;
  return events.every((e) => fields.every((field) => (e as unknown as Record<string, unknown>)[field] !== undefined));
}

export interface EvaluationResult {
  outcomes: PredicateOutcome[];
  overallVerdict: Verdict;
}

// Mirrors Algorithm 1 from the design notes: missing evidence short-circuits
// to INCONCLUSIVE before any predicate runs, mandatory-predicate FAIL beats
// everything else, otherwise PASS.
export function evaluate(profile: ControlProfile, events: NormalizedEvent[]): EvaluationResult {
  const outcomes: PredicateOutcome[] = [];

  for (const control of profile.controls) {
    if (!requiredEvidencePresent(events, control.evidence)) {
      outcomes.push({
        controlId: control.control_id,
        predicateId: control.predicate,
        verdict: 'INCONCLUSIVE',
        reason: `missing required evidence fields: ${control.evidence.join(', ')}`,
        evidenceSeqs: [],
      });
      continue;
    }

    const predicateFn = predicateRegistry[control.predicate];
    if (!predicateFn) {
      outcomes.push({
        controlId: control.control_id,
        predicateId: control.predicate,
        verdict: 'INCONCLUSIVE',
        reason: `predicate "${control.predicate}" is not registered`,
        evidenceSeqs: [],
      });
      continue;
    }

    const result = predicateFn(events, control.theta);
    outcomes.push({ controlId: control.control_id, predicateId: control.predicate, ...result });
  }

  const mandatoryControlIds = new Set(profile.controls.filter((c) => c.mandatory).map((c) => c.control_id));
  const anyMandatoryFail = outcomes.some((o) => mandatoryControlIds.has(o.controlId) && o.verdict === 'FAIL');
  const allMandatoryPass = outcomes
    .filter((o) => mandatoryControlIds.has(o.controlId))
    .every((o) => o.verdict === 'PASS');

  let overallVerdict: Verdict;
  if (anyMandatoryFail) {
    overallVerdict = 'FAIL';
  } else if (allMandatoryPass) {
    overallVerdict = 'PASS';
  } else {
    overallVerdict = 'INCONCLUSIVE';
  }

  return { outcomes, overallVerdict };
}

export function loadProfiles(...relativePaths: string[]): ControlProfile {
  const merged: ControlProfile = { version: 1, controls: [] };
  for (const relativePath of relativePaths) {
    const profile = loadProfile(path.resolve(process.cwd(), relativePath));
    merged.controls.push(...profile.controls);
  }
  return merged;
}
