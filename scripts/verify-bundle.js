// Standalone verifier - reruns the same hash computation as seal.ts against
// an already-written bundle. If this disagrees with manifest.json, the
// bundle was altered after the run and should not be trusted as evidence.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function sha256(content) {
  return crypto.createHash('sha256').update(content).digest('hex');
}

function verifyBundle(runDir) {
  const manifestPath = path.join(runDir, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

  const eventsJsonl = fs.readFileSync(path.join(runDir, 'events.jsonl'), 'utf8');
  const verdictsJson = fs.readFileSync(path.join(runDir, 'verdicts.json'), 'utf8');

  const problems = [];

  const actualEventsHash = sha256(eventsJsonl);
  if (actualEventsHash !== manifest.files['events.jsonl']) {
    problems.push(`events.jsonl hash mismatch: manifest=${manifest.files['events.jsonl']} actual=${actualEventsHash}`);
  }

  const actualVerdictsHash = sha256(verdictsJson);
  if (actualVerdictsHash !== manifest.files['verdicts.json']) {
    problems.push(`verdicts.json hash mismatch: manifest=${manifest.files['verdicts.json']} actual=${actualVerdictsHash}`);
  }

  const { bundleSha256, ...manifestBody } = manifest;
  const actualBundleHash = sha256(eventsJsonl + verdictsJson + JSON.stringify(manifestBody));
  if (actualBundleHash !== bundleSha256) {
    problems.push(`bundle hash mismatch: manifest=${bundleSha256} actual=${actualBundleHash}`);
  }

  return { runId: manifest.runId, ok: problems.length === 0, problems };
}

function main() {
  const target = process.argv[2] || 'evidence-runs';
  if (!fs.existsSync(target)) {
    console.error(`no such path: ${target}`);
    process.exit(1);
  }

  const runDirs = fs.statSync(target).isDirectory() && fs.existsSync(path.join(target, 'manifest.json'))
    ? [target]
    : fs.readdirSync(target)
      .map((name) => path.join(target, name))
      .filter((p) => fs.existsSync(path.join(p, 'manifest.json')));

  if (runDirs.length === 0) {
    console.log(`no evidence bundles found under ${target}`);
    return;
  }

  let anyFailed = false;
  for (const runDir of runDirs) {
    const result = verifyBundle(runDir);
    if (result.ok) {
      console.log(`OK    ${result.runId}`);
    } else {
      anyFailed = true;
      console.log(`FAIL  ${result.runId}`);
      result.problems.forEach((p) => console.log(`        ${p}`));
    }
  }

  process.exit(anyFailed ? 1 : 0);
}

main();
