'use strict';

const $ = (id) => document.getElementById(id);
const audio = $('audio');
const form = $('reader-form');
const notes = $('notes');
const voice = $('voice');
const pace = $('pace');
let config;
let currentRecording;
let recordings = [];
let busy = false;
const draftKey = 'suno-study-draft-v1';

const languageName = (code) => code === 'hi-IN' ? 'Hindi' : 'English';
const language = () => form.querySelector('input[name="language"]:checked').value;
const characterCount = (text) => [...text].length;
const options = () => ({text: notes.value.trim(), language: language(), speaker: voice.value, pace: Number(pace.value)});
const identity = (value) => JSON.stringify([value.text.trim(), value.language, value.speaker, Number(value.pace)]);
const matchingRecording = () => recordings.find((item) => identity(item) === identity(options()));
const money = (amount) => `₹${amount.toFixed(amount > 0 && amount < 0.01 ? 3 : 2)}`;
const time = (seconds) => `${Math.floor((Number.isFinite(seconds) ? seconds : 0) / 60)}:${String(Math.floor((Number.isFinite(seconds) ? seconds : 0) % 60)).padStart(2, '0')}`;

function clearError() { $('error-message').hidden = true; $('error-message').textContent = ''; }
function showError(message) { $('error-message').textContent = message; $('error-message').hidden = false; }
function showStatus(message) { $('status-message').textContent = message; }

function saveDraft() {
  try { localStorage.setItem(draftKey, JSON.stringify(options())); } catch { /* Private browsing may disable local storage. */ }
}

function updateEditor() {
  if (!config) return;
  const text = notes.value.trim();
  const count = characterCount(text);
  const overLimit = count > config.max_characters;
  $('character-count').textContent = `${count.toLocaleString('en-IN')} / 2,000 characters`;
  $('character-count').classList.toggle('over-limit', overLimit);
  notes.setAttribute('aria-invalid', String(overLimit));
  const paragraphs = text ? text.split(/\n\s*\n/).filter((item) => item.trim()).length : 0;
  $('paragraph-count').textContent = `${paragraphs} ${paragraphs === 1 ? 'paragraph' : 'paragraphs'}`;
  $('sample-marker').hidden = text !== config.samples[language()];
  notes.lang = language() === 'hi-IN' ? 'hi' : 'en';
  $('pace-value').value = `${Number(pace.value)}×`;
  const cached = matchingRecording();
  const estimate = cached ? 0 : count / 1000 * config.rate_per_1000_inr;
  $('estimate-label').textContent = cached ? 'Already in your library' : 'Estimated generation cost';
  $('cost-estimate').textContent = cached ? '₹0 to replay' : money(estimate);
  $('generate-label').textContent = busy ? 'Creating your audio…' : cached ? 'Load saved audio' : 'Generate audio';
  $('generate-button').disabled = busy || !text || overLimit;
  $('cost-note').textContent = cached ? 'Same notes, same voice. No new generation needed.' : '₹1 / 1,000 characters · estimate before GST';
  $('voice-description').textContent = config.voices[language()].find((item) => item.id === voice.value)?.style || '';
  saveDraft();
}

function populateVoices(selected) {
  voice.replaceChildren();
  for (const narrator of config.voices[language()]) {
    const option = document.createElement('option');
    option.value = narrator.id;
    option.textContent = narrator.name;
    voice.append(option);
  }
  if (config.voices[language()].some((item) => item.id === selected)) voice.value = selected;
}

function setOptions(value) {
  const radio = [...form.querySelectorAll('input[name="language"]')].find((input) => input.value === value.language);
  if (radio) radio.checked = true;
  populateVoices(value.speaker);
  pace.value = Number.isFinite(Number(value.pace)) ? value.pace : 1;
  notes.value = typeof value.text === 'string' ? value.text : '';
  updateEditor();
}

function drawWaveform(recording) {
  const svg = $('waveform');
  svg.replaceChildren();
  const peaks = recording.peaks || [];
  if (!peaks.length) return;
  peaks.forEach((peak, index) => {
    const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    const height = Math.max(3, peak * 50);
    bar.setAttribute('x', String(index * (800 / peaks.length)));
    bar.setAttribute('y', String((56 - height) / 2));
    bar.setAttribute('width', String(Math.max(2, 800 / peaks.length - 5)));
    bar.setAttribute('height', String(height));
    bar.setAttribute('rx', '2');
    svg.append(bar);
  });
}

function updatePlayback() {
  const duration = Number.isFinite(audio.duration) ? audio.duration : currentRecording?.seconds || 0;
  const progress = duration ? audio.currentTime / duration : 0;
  $('seek').max = String(duration || 1);
  $('seek').value = String(audio.currentTime || 0);
  $('seek').setAttribute('aria-valuetext', `${time(audio.currentTime)} of ${time(duration)}`);
  $('current-time').textContent = time(audio.currentTime);
  $('total-time').textContent = time(duration);
  [...$('waveform').children].forEach((bar, index, bars) => bar.classList.toggle('played', (index + 0.5) / bars.length <= progress));
  const playing = !audio.paused && !audio.ended;
  $('play-icon').setAttribute('href', playing ? '#i-pause' : '#i-play');
  $('play-button').setAttribute('aria-label', playing ? 'Pause recording' : 'Play recording');
}

function showRecording(recording) {
  audio.pause();
  currentRecording = recording;
  audio.src = recording.audio_url;
  audio.load();
  $('player-empty').hidden = true;
  $('player-content').hidden = false;
  $('download-button').hidden = false;
  $('download-button').href = recording.download_url;
  $('download-button').download = `suno-${recording.language}-${recording.id.slice(0, 8)}.wav`;
  $('player-heading').textContent = `Your notes, in ${languageName(recording.language)}.`;
  $('recording-excerpt').textContent = recording.text;
  $('recording-excerpt').lang = recording.language === 'hi-IN' ? 'hi' : 'en';
  const narrator = config.voices[recording.language]?.find((item) => item.id === recording.speaker)?.name || recording.speaker;
  $('recording-details').textContent = `${recording.characters} characters · ${narrator} · ${recording.pace}× · ${money(recording.estimated_cost_inr)} original estimate`;
  drawWaveform(recording);
  updatePlayback();
}

function makeRecordingButton(recording) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'recent-recording';
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.classList.add('icon');
  icon.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#i-wave');
  icon.append(use);
  const text = document.createElement('span');
  text.className = 'recent-text';
  const title = document.createElement('strong');
  title.textContent = recording.text.replace(/\s+/g, ' ');
  title.lang = recording.language === 'hi-IN' ? 'hi' : 'en';
  const detail = document.createElement('small');
  detail.textContent = `${languageName(recording.language)} · ${time(recording.seconds)} · Saved`;
  text.append(title, detail);
  button.append(icon, text);
  button.addEventListener('click', () => {
    if (busy) return;
    clearError();
    setOptions(recording);
    showRecording(recording);
    $('library-dialog').close();
    showStatus('Saved recording loaded. No credits used.');
  });
  return button;
}

function renderLibrary() {
  $('saved-count').textContent = String(recordings.length);
  for (const [target, limit] of [[$('recent-list'), 5], [$('library-list'), 10]]) {
    target.replaceChildren();
    if (!recordings.length) {
      const empty = document.createElement('p');
      empty.className = 'quiet-note';
      empty.textContent = 'Your recordings will appear here after you generate audio.';
      target.append(empty);
    }
    recordings.slice(0, limit).forEach((recording) => target.append(makeRecordingButton(recording)));
  }
}

function setBusy(value) {
  busy = value;
  form.setAttribute('aria-busy', String(value));
  [...form.querySelectorAll('textarea, input, select, button')].forEach((control) => { control.disabled = value; });
  $('generate-button').querySelector('.spinner').hidden = !value;
  $('generate-button').querySelector('.button-arrow').hidden = value;
  updateEditor();
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !config) return;
  clearError();
  const payload = options();
  const count = characterCount(payload.text);
  if (!count || count > config.max_characters) { showError('Add between 1 and 2,000 characters of study notes.'); return; }
  const existing = matchingRecording();
  if (existing) {
    showRecording(existing);
    showStatus('Your saved audio is ready. No new request or charge.');
    return;
  }
  setBusy(true);
  showStatus('Finding the rhythm in your notes. This may take a moment…');
  try {
    const response = await fetch('/api/generate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The recording could not be generated.');
    const recording = data.recording;
    recordings = [recording, ...recordings.filter((item) => item.id !== recording.id)].slice(0, 10);
    renderLibrary();
    showRecording(recording);
    showStatus(recording.cached ? 'Saved audio loaded. No new generation charge.' : `Your recording is ready. Estimated generation cost ${money(recording.generation_estimate_inr)} before GST.`);
  } catch (error) {
    showStatus('');
    showError(error instanceof TypeError ? 'Connection lost. Check that the local reader is running. Your notes are still here. Reload before generating again; the recording may already be saved.' : error.message);
  } finally {
    setBusy(false);
  }
});

notes.addEventListener('input', () => { clearError(); showStatus(''); updateEditor(); });
voice.addEventListener('change', () => { clearError(); updateEditor(); });
pace.addEventListener('input', updateEditor);
form.querySelectorAll('input[name="language"]').forEach((radio) => radio.addEventListener('change', () => { clearError(); populateVoices(); updateEditor(); }));
$('clear-button').addEventListener('click', () => { notes.value = ''; clearError(); showStatus(''); updateEditor(); notes.focus(); });
for (const [id, code] of [['hindi-sample', 'hi-IN'], ['english-sample', 'en-IN']]) {
  $(id).addEventListener('click', () => { setOptions({text: config.samples[code], language: code, speaker: config.voices[code][0].id, pace: 1}); clearError(); showStatus('Sample notes loaded. Audio is generated only when you choose Generate.'); });
}
$('play-button').addEventListener('click', async () => {
  try { if (audio.paused) await audio.play(); else audio.pause(); }
  catch { showError('The saved audio could not be played. Try downloading the recording, or reload the reader.'); }
});
$('seek').addEventListener('input', () => { if (Number.isFinite(audio.duration)) audio.currentTime = Number($('seek').value); updatePlayback(); });
$('skip-back').addEventListener('click', () => { audio.currentTime = Math.max(0, audio.currentTime - 10); updatePlayback(); });
$('skip-forward').addEventListener('click', () => { if (Number.isFinite(audio.duration)) audio.currentTime = Math.min(audio.duration, audio.currentTime + 10); updatePlayback(); });
for (const event of ['timeupdate', 'loadedmetadata', 'play', 'pause', 'ended']) audio.addEventListener(event, updatePlayback);
audio.addEventListener('error', () => { if (currentRecording) showError('This audio file could not be loaded. Reload the reader to check saved recordings.'); });
$('help-button').addEventListener('click', () => $('help-dialog').showModal());
$('library-button').addEventListener('click', () => $('library-dialog').showModal());
document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => $(button.dataset.close).close()));
document.querySelectorAll('dialog').forEach((dialog) => dialog.addEventListener('click', (event) => { if (event.target === dialog) { const bounds = dialog.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close(); } }));

async function initialize() {
  setBusy(true);
  try {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('The reader could not load its settings. Restart the local server and reload.');
    config = await response.json();
    recordings = config.recent;
    renderLibrary();
    let draft;
    try { draft = JSON.parse(localStorage.getItem(draftKey)); } catch { /* Use the sample on first visit. */ }
    setOptions(draft && ['hi-IN', 'en-IN'].includes(draft.language) ? draft : {text: config.samples['hi-IN'], language: 'hi-IN', speaker: config.voices['hi-IN'][0].id, pace: 1});
    if (recordings.length) showRecording(matchingRecording() || recordings[0]);
    setBusy(false);
  } catch (error) {
    showError(error.message || 'Unable to connect to the local reader.');
  }
}

initialize();
