document.getElementById('otp-verify-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const errorEl = document.getElementById('otp-error');
  const code = document.getElementById('code').value;

  const res = await fetch('/otp/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  const result = await res.json();

  if (result.outcome === 'accept') {
    window.location.href = '/dashboard';
    return;
  }
  errorEl.textContent = `Rejected: ${result.reason}`;
});
