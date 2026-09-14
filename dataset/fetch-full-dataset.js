// Pulls the RBA dataset from its Zenodo record via the public REST API
// (documented at https://developers.zenodo.org/#records). Record ID matches
// the DOI cited in the accompanying paper: 10.5281/zenodo.6782155.
const fs = require('fs');
const path = require('path');
const https = require('https');

const RECORD_ID = '6782155';
const OUT_PATH = path.join(__dirname, 'rba-full.csv');

function getJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'otp-fido2-compliance-poc' } }, (res) => {
      if (res.statusCode !== 200) {
        reject(new Error(`GET ${url} returned ${res.statusCode}`));
        return;
      }
      let raw = '';
      res.on('data', (chunk) => { raw += chunk; });
      res.on('end', () => resolve(JSON.parse(raw)));
    }).on('error', reject);
  });
}

function downloadFile(url, outPath) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'otp-fido2-compliance-poc' } }, (res) => {
      if (res.statusCode !== 200) {
        reject(new Error(`GET ${url} returned ${res.statusCode}`));
        return;
      }
      const file = fs.createWriteStream(outPath);
      res.pipe(file);
      file.on('finish', () => file.close(resolve));
    }).on('error', reject);
  });
}

async function main() {
  console.log(`fetching record metadata for Zenodo ${RECORD_ID}...`);
  const record = await getJson(`https://zenodo.org/api/records/${RECORD_ID}`);
  const files = record.files || [];
  if (files.length === 0) {
    console.error('no files listed on this Zenodo record - check the record ID is still valid');
    process.exit(1);
  }

  const target = files.find((f) => /\.(csv|zip)$/i.test(f.key)) || files[0];
  const downloadUrl = target.links?.self;
  if (!downloadUrl) {
    console.error('could not find a download link on the file entry - Zenodo API response shape may have changed');
    process.exit(1);
  }

  console.log(`downloading ${target.key} (${Math.round((target.size || 0) / 1e6)} MB) to ${OUT_PATH}...`);
  await downloadFile(downloadUrl, OUT_PATH.replace(/\.csv$/, target.key.endsWith('.zip') ? '.zip' : '.csv'));
  console.log('done. Unzip if needed - this script does not extract archives.');
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
