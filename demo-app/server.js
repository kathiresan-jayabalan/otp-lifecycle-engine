require('dotenv').config();
const path = require('path');
const express = require('express');
const session = require('express-session');

const clock = require('./lib/clock');
const eventLog = require('./lib/eventLog');
const userStore = require('./lib/userStore');
const otpStore = require('./lib/otpStore');
const channelRouter = require('./lib/channels/channelRouter');
const localSimulator = require('./lib/channels/localSimulator');

const app = express();
const PORT = Number(process.env.DEMO_APP_PORT || 4000);
const IS_PROD = process.env.NODE_ENV === 'production';

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(express.static(path.join(__dirname, 'public')));
app.use(session({
  secret: process.env.DEMO_APP_SESSION_SECRET || 'dev-only-secret',
  resave: false,
  saveUninitialized: true,
}));

function requireAuth(req, res, next) {
  if (!req.session.authenticated) return res.redirect('/login');
  next();
}

app.get('/', (req, res) => res.render('index', { error: null }));

app.post('/signup', (req, res) => {
  const { email, phone } = req.body;
  if (!email) return res.render('index', { error: 'Email is required' });
  userStore.upsert(email, phone);
  res.redirect('/login');
});

app.get('/login', (req, res) => res.render('login', { error: null }));

app.post('/login/otp/start', async (req, res) => {
  const { email, channel } = req.body;
  const user = userStore.find(email);
  if (!user) return res.render('login', { error: 'No account with that email - sign up first' });

  userStore.unlockIfExpired(user.subjectId, clock.now());
  if (user.locked) return res.render('login', { error: 'Account temporarily locked, try again later' });

  const destination = channel === 'sms' ? user.phone : user.email;
  if (!destination) return res.render('login', { error: `No ${channel} on file for this account` });

  const { code } = otpStore.issue(user.subjectId, channel, req.sessionID);
  const delivery = await channelRouter.deliver(channel, destination, code);
  otpStore.markDelivered(user.subjectId, channel, req.sessionID, delivery);

  req.session.pending = { subjectId: user.subjectId, channel };
  res.redirect('/otp');
});

app.get('/otp', (req, res) => {
  if (!req.session.pending) return res.redirect('/login');
  res.render('otp', { error: null, channel: req.session.pending.channel });
});

// Always JSON, same shape whether the caller is the otp.ejs client script or
// a test driving the API directly. subjectId/channel are read from the body
// when present so a session that never called /login/otp/start (a second,
// independent browser session in the cross-session test) can still attempt
// a verification against someone else's outstanding code.
app.post('/otp/verify', (req, res) => {
  const pending = req.session.pending;
  const subjectId = req.body.subjectId || pending?.subjectId;
  const channel = req.body.channel || pending?.channel;

  if (!subjectId || !channel) {
    return res.status(400).json({ outcome: 'reject', reason: 'no_pending_verification' });
  }

  const result = otpStore.verify(subjectId, channel, req.sessionID, req.body.code);
  if (result.outcome === 'accept') {
    req.session.authenticated = true;
    req.session.subjectId = subjectId;
    delete req.session.pending;
    return res.json({ outcome: 'accept' });
  }

  if (result.reason === 'locked') {
    userStore.lock(subjectId, clock.now() + otpStore.LOCKOUT_MS);
  }

  res.json({ outcome: result.outcome, reason: result.reason });
});

app.get('/dashboard', requireAuth, (req, res) => {
  res.render('dashboard', { subjectId: req.session.subjectId });
});

app.get('/logout', (req, res) => {
  req.session.destroy(() => res.redirect('/'));
});

// Test-only introspection surface. Never mounted in a production NODE_ENV.
if (!IS_PROD) {
  app.get('/internal/events', (req, res) => {
    const since = Number(req.query.since || 0);
    const subject = req.query.subject;
    const events = subject ? eventLog.forSubject(subject) : eventLog.since(since);
    res.json(events);
  });

  app.post('/internal/clock/advance', (req, res) => {
    const newOffset = clock.advance(Number(req.body.ms || 0));
    res.json({ offsetMs: newOffset });
  });

  app.post('/internal/clock/reset', (req, res) => {
    clock.reset();
    res.json({ ok: true });
  });

  app.get('/internal/simulator/inbox', (req, res) => {
    const message = localSimulator.latestFor(req.query.to);
    res.json(message);
  });

  app.post('/internal/reset', (req, res) => {
    clock.reset();
    eventLog.reset();
    userStore.reset();
    otpStore.reset();
    localSimulator.reset();
    res.json({ ok: true });
  });
}

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`demo app listening on http://localhost:${PORT}`);
    console.log(`email channel mode: ${channelRouter.modeFor('email')}`);
    console.log(`sms channel mode:   ${channelRouter.modeFor('sms')}`);
  });
}

module.exports = app;
