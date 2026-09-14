export type EventAction =
  | 'issue'
  | 'deliver'
  | 'supersede'
  | 'accept'
  | 'reject'
  | 'lock'
  | 'register'
  | 'revoke';

export interface NormalizedEvent {
  seq: number;
  observerTime: number;
  sourceTime: number;
  subject: string;
  session: string;
  mechanism: string;
  action: EventAction;
  channel: string;
  meta: Record<string, unknown>;
}

export type Verdict = 'PASS' | 'FAIL' | 'INCONCLUSIVE';

export interface PredicateOutcome {
  controlId: string;
  predicateId: string;
  verdict: Verdict;
  reason: string;
  evidenceSeqs: number[];
}

export interface ControlDefinition {
  control_id: string;
  source: string;
  source_version: string;
  clause: string;
  clause_verified: boolean;
  paraphrase: string;
  predicate: string;
  mandatory: boolean;
  theta: Record<string, unknown>;
  evidence: string[];
}

export interface ControlProfile {
  version: number;
  controls: ControlDefinition[];
}

export type PredicateFn = (
  events: NormalizedEvent[],
  theta: Record<string, unknown>,
) => Omit<PredicateOutcome, 'controlId' | 'predicateId'>;
