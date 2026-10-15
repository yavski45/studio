const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function editor() {
  const revoked = [], calls = {load: 0, pause: 0, submit: 0, dialog: 0};
  const sandbox = {window: {}, URL: {createObjectURL: () => 'blob:local', revokeObjectURL: url => revoked.push(url)},
    matchMedia: () => ({matches: true}), cancelAnimationFrame() {}, devicePixelRatio: 1};
  vm.runInNewContext(fs.readFileSync(__dirname + '/../static/studio/editor.js', 'utf8'), sandbox);
  const state = sandbox.window.dublaoStudio();
  state.$nextTick = callback => callback();
  state.$refs = {video: {currentTime: 0, paused: true, pause() {calls.pause++;}, load() {calls.load++;}},
    uploadForm: {requestSubmit() {calls.submit++;}},
    confirmation: {showModal() {calls.dialog++;}, close() {}}};
  return {state, calls, revoked, sandbox};
}

test('minute entamée par langue, including exact boundaries and unknown duration', () => {
  const {state} = editor();
  state.selectedLanguages = [{locale: 'fr_FR'}, {locale: 'en_US'}];
  assert.equal(state.estimate, null);
  for (const [duration, expected] of [[1, 2], [60, 2], [60.001, 4], [61, 4], [120, 4], [120.001, 6]]) {
    state.originalDuration = duration;
    assert.equal(state.estimate, expected);
  }
  state.availableUnits = 5 * 60000;
  assert.equal(state.insufficient, true);
  state.availableUnits = 6 * 60000;
  assert.equal(state.insufficient, false);
});

test('status updates preserve current playback and use actual wallet state', () => {
  const {state, calls} = editor();
  state.mode = 'project'; state.currentUrl = '/original/lecture/'; state.currentTime = 42; state.playing = true;
  state.syncState({versions: [{locale: 'en_US', state: 'ready', watchUrl: '/output/lecture/'}],
    status: 'completed', availableUnits: 120000, reservedUnits: 0, consumedUnits: 60000,
    reservationStatus: 'captured', reservationUnits: 60000, frozen: false, errorMessage: '', resumeUrl: ''});
  assert.equal(state.currentUrl, '/original/lecture/');
  assert.equal(state.currentTime, 42);
  assert.equal(state.playing, true);
  assert.equal(calls.load, 0);
  assert.equal(calls.pause, 0);
  assert.equal(state.availableUnits, 120000);
  assert.equal(state.reservationStatus, 'captured');
});

test('first available output loads when original cannot be played', () => {
  const {state, calls} = editor(); state.mode = 'project';
  state.syncState({versions: [{locale: 'en_US', state: 'ready', name: 'Anglais', watchUrl: '/output/lecture/', downloadUrl: '/download/'}]});
  assert.equal(state.selectedVersion, 'en_US');
  assert.equal(state.$refs.video.src, '/output/lecture/');
  assert.equal(state.selectedDownloadUrl, '/download/');
  assert.equal(calls.load, 1);
});

test('seeking is bounded; volume and mute use native media properties', () => {
  const {state} = editor(); state.duration = 90;
  state.seekTo(500); assert.equal(state.$refs.video.currentTime, 90);
  state.seekTo(-5); assert.equal(state.$refs.video.currentTime, 0);
  state.seekTo(32.5); assert.equal(state.currentTime, 32.5);
  state.setVolume(2); assert.equal(state.$refs.video.volume, 1);
  state.toggleMute(); assert.equal(state.$refs.video.muted, true);
  assert.equal(state.time(3661), '1:01:01');
});

test('imports keep large videos usable and release local URLs', () => {
  const {state, calls, revoked} = editor();
  state.importFile({target: {files: [{name: 'Long film.mp4', size: 200 * 1024 * 1024}]}});
  assert.equal(state.title, 'Long film');
  assert.equal(state.currentUrl, 'blob:local');
  assert.equal(state.canAnalyzeAudio, false);
  assert.equal(state.hasWaveform, false);
  assert.equal(calls.load, 1);
  state.destroy(); assert.deepEqual(revoked, ['blob:local']);
});

test('launch confirmation submits once and insufficient balance prevents launch', () => {
  const {state, calls} = editor();
  state.updateSelection = () => {};
  let prevented = 0;
  const event = {preventDefault() {prevented++;}};
  state.availableUnits = 120000; state.originalDuration = 61; state.selectedLanguages = [{locale: 'en_US'}];
  state.handleSubmit(event); assert.equal(prevented, 1); assert.equal(calls.dialog, 1);
  state.confirmLaunch(); assert.equal(calls.submit, 1);
  state.handleSubmit(event); assert.equal(state.sending, true);
  state.handleSubmit(event); assert.equal(prevented, 2);
  const blocked = editor(); blocked.state.selectedLanguages = [{locale: 'en_US'}];
  blocked.state.confirmLaunch(); assert.equal(blocked.calls.submit, 0);
});
