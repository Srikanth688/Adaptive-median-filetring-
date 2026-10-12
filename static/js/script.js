const $ = (selector) => document.querySelector(selector);
const imageInput = $('#image-input');
const uploadButton = $('#upload-button');
const noiseButton = $('#noise-button');
const restoreButton = $('#restore-button');
const downloadButton = $('#download-button');
const messageBox = $('#message');
const densityInput = $('#noise-density');
const windowSelect = $('#window-size');
const filterRadios = [...document.querySelectorAll('input[name="filter"]')];

const state = {
  imageId: null,
  originalUrl: null,
  noisyUrl: null,
  restored: { standard: null, adaptive: null },
  download: { standard: null, adaptive: null },
  metrics: { noisy: null, standard: null, adaptive: null },
  filename: null,
  width: null,
  height: null,
};
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ACCEPTED_TYPES = ['image/png', 'image/jpeg'];

function showMessage(text, kind = 'info') {
  messageBox.textContent = text;
  messageBox.className = `notice ${kind}`;
  messageBox.hidden = !text;
}
function setLoading(id, active) { $(`#${id}`).hidden = !active; }
function setLocked(sectionId, locked) { $(`#${sectionId}`).classList.toggle('locked', locked); }
function getSelectedFilter() { return filterRadios.find((radio) => radio.checked)?.value || 'adaptive'; }
function updateWorkflow() {
  const uploaded = Boolean(state.imageId);
  const noisy = Boolean(state.noisyUrl);
  $('#noise-lock').textContent = uploaded ? 'Ready' : 'Upload an image first';
  $('#restore-lock').textContent = noisy ? 'Ready' : 'Generate noise first';
  setLocked('noise-section', !uploaded);
  setLocked('restore-section', !noisy);
  noiseButton.disabled = !uploaded;
  restoreButton.disabled = !noisy;
  uploadButton.disabled = !imageInput.files[0];
  const step = !uploaded ? 1 : !noisy ? 2 : (!state.restored.standard && !state.restored.adaptive) ? 3 : 4;
  document.querySelectorAll('.workflow-step').forEach((el) => {
    el.classList.toggle('active', Number(el.dataset.step) === step);
    el.classList.toggle('complete', Number(el.dataset.step) < step);
  });
  const count = [state.originalUrl, state.noisyUrl, state.restored.standard, state.restored.adaptive].filter(Boolean).length;
  $('#result-count').textContent = `${count} / 4 images`;
}
function renderPanel(kind, url, metaText) {
  const stage = $(`#stage-${kind}`);
  stage.replaceChildren();
  stage.classList.remove('empty');
  const image = document.createElement('img');
  image.src = `${url}${url.includes('?') ? '&' : '?'}v=${Date.now()}`;
  image.alt = `${kind} image result`;
  image.addEventListener('error', () => {
    stage.replaceChildren();
    stage.classList.add('empty');
    const errorText = document.createElement('span');
    errorText.textContent = 'Could not load this image. Please process it again.';
    stage.append(errorText);
  }, { once: true });
  stage.append(image);
  $(`#state-${kind}`).textContent = 'Generated';
  $(`#state-${kind}`).classList.add('available');
  $(`#meta-${kind}`).textContent = metaText;
}
function resetPanel(kind, placeholder) {
  const stage = $(`#stage-${kind}`);
  stage.replaceChildren();
  stage.classList.add('empty');
  const text = document.createElement('span');
  text.textContent = placeholder;
  stage.append(text);
  $(`#state-${kind}`).textContent = 'Waiting';
  $(`#state-${kind}`).classList.remove('available');
  $(`#meta-${kind}`).textContent = 'Not generated';
}
function formatMetric(value, digits = 4) {
  if (value === null || value === undefined) return 'Unavailable';
  if (value === 'Infinity') return '∞';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : 'Unavailable';
}
function updateMetrics() {
  const body = $('#metrics-body');
  body.replaceChildren();
  const rows = [
    ['Noisy image', state.metrics.noisy],
    ['Standard median', state.metrics.standard],
    ['Adaptive median', state.metrics.adaptive],
  ].filter(([, metrics]) => metrics);
  if (!rows.length) {
    const tr = document.createElement('tr'); tr.className = 'empty-row';
    const td = document.createElement('td'); td.colSpan = 4;
    td.textContent = 'Upload an image and process it to calculate real quality metrics.';
    tr.append(td); body.append(tr); return;
  }
  rows.forEach(([label, metric]) => {
    const tr = document.createElement('tr');
    [label, formatMetric(metric.mse), formatMetric(metric.psnr), formatMetric(metric.ssim, 5)].forEach((value) => {
      const td = document.createElement('td'); td.textContent = value; tr.append(td);
    });
    body.append(tr);
  });
  $('#metrics-note').textContent = 'MSE, PSNR, and SSIM are calculated from the original image and each generated result. A PSNR of ∞ means the compared images are identical.';
}
async function requestJson(url, options) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { throw new Error(`Server returned an unreadable response (${response.status}).`); }
  if (!response.ok || data.ok === false) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

imageInput.addEventListener('change', () => {
  const file = imageInput.files[0];
  showMessage('');
  if (!file) { uploadButton.disabled = true; return; }
  if (!ACCEPTED_TYPES.includes(file.type) || !/\.(png|jpe?g)$/i.test(file.name)) {
    imageInput.value = ''; uploadButton.disabled = true;
    showMessage('Please choose a PNG, JPG, or JPEG image.', 'error'); return;
  }
  if (file.size > MAX_FILE_SIZE) {
    imageInput.value = ''; uploadButton.disabled = true;
    showMessage('This file is larger than 10 MB. Choose a smaller image.', 'error'); return;
  }
  uploadButton.disabled = false;
  $('#upload-summary').innerHTML = `<div class="file-pill">PNG / JPG</div><strong>${escapeHtml(file.name)}</strong><p>${(file.size / 1024).toFixed(1)} KB · Ready to upload</p>`;
  showMessage('Image selected. Upload it to start processing.', 'info');
});
function escapeHtml(value) { return value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]); }

$('#drop-zone').addEventListener('dragover', (event) => { event.preventDefault(); $('#drop-zone').classList.add('dragging'); });
$('#drop-zone').addEventListener('dragleave', () => $('#drop-zone').classList.remove('dragging'));
$('#drop-zone').addEventListener('drop', (event) => {
  event.preventDefault(); $('#drop-zone').classList.remove('dragging');
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer(); transfer.items.add(file); imageInput.files = transfer.files;
  imageInput.dispatchEvent(new Event('change', { bubbles: true }));
});

uploadButton.addEventListener('click', async () => {
  const file = imageInput.files[0]; if (!file) return;
  uploadButton.disabled = true; setLoading('upload-loading', true); showMessage('');
  try {
    const formData = new FormData(); formData.append('image', file);
    const result = await requestJson('/upload', { method: 'POST', body: formData });
    state.imageId = result.image_id; state.originalUrl = result.original; state.noisyUrl = null;
    state.restored = { standard: null, adaptive: null }; state.download = { standard: null, adaptive: null };
    state.metrics = { noisy: null, standard: null, adaptive: null };
    state.filename = result.filename; state.width = result.width; state.height = result.height;
    renderPanel('original', result.original, `${result.width} × ${result.height} px · ${result.filename}`);
    resetPanel('noisy', 'Generate noise to view'); resetPanel('standard', 'Run the standard filter'); resetPanel('adaptive', 'Run the adaptive filter');
    $('#upload-summary').innerHTML = `<div class="file-pill success-pill">✓ UPLOADED</div><strong>${escapeHtml(result.filename)}</strong><p>${result.width} × ${result.height} pixels · RGB image</p><span class="summary-note">Original image stored separately and left unchanged.</span>`;
    updateMetrics(); updateWorkflow(); showMessage('Image uploaded and validated successfully.', 'success');
    $('#noise-section').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (error) { showMessage(error.message, 'error'); }
  finally { setLoading('upload-loading', false); uploadButton.disabled = !imageInput.files[0]; }
});

densityInput.addEventListener('input', () => { $('#density-value').textContent = `${Math.round(Number(densityInput.value) * 100)}%`; });
noiseButton.addEventListener('click', async () => {
  if (!state.imageId) return;
  noiseButton.disabled = true; setLoading('noise-loading', true); showMessage('');
  try {
    const result = await requestJson('/add-noise', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_id: state.imageId, noise_density: Number(densityInput.value) }) });
    state.noisyUrl = result.noisy; state.metrics.noisy = result.metrics;
    state.restored = { standard: null, adaptive: null }; state.download = { standard: null, adaptive: null };
    renderPanel('noisy', result.noisy, `${Math.round(result.density * 100)}% density · ${state.width} × ${state.height} px`);
    resetPanel('standard', 'Run the standard filter'); resetPanel('adaptive', 'Run the adaptive filter');
    downloadButton.disabled = true; updateMetrics(); updateWorkflow(); showMessage(result.message, 'success');
    $('#restore-section').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (error) { showMessage(error.message, 'error'); }
  finally { setLoading('noise-loading', false); noiseButton.disabled = !state.imageId; }
});

function updateFilterSelection() {
  const filter = getSelectedFilter();
  $('#standard-option').classList.toggle('selected', filter === 'standard');
  $('#adaptive-option').classList.toggle('selected', filter === 'adaptive');
  $('#window-label').textContent = filter === 'standard' ? 'Median window size' : 'Maximum adaptive window';
  $('#window-help').textContent = filter === 'standard'
    ? 'One fixed odd-sized neighborhood is used for every pixel.'
    : 'Adaptive filtering starts at 3 × 3 and grows up to this maximum.';
}
filterRadios.forEach((radio) => radio.addEventListener('change', updateFilterSelection));

restoreButton.addEventListener('click', async () => {
  if (!state.imageId || !state.noisyUrl) return;
  const filter = getSelectedFilter(); const windowSize = Number(windowSelect.value);
  restoreButton.disabled = true; setLoading('restore-loading', true); showMessage('');
  try {
    const body = { image_id: state.imageId, filter };
    if (filter === 'standard') body.window_size = windowSize; else body.max_window = windowSize;
    const result = await requestJson('/remove-noise', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    state.restored[filter] = result.image; state.download[filter] = result.download; state.metrics[filter] = result.metrics;
    renderPanel(filter, result.image, `${result.filter_label} · ${windowSize} × ${windowSize} max · ${result.processing_ms} ms`);
    downloadButton.disabled = false; downloadButton.dataset.filter = filter;
    updateMetrics(); updateWorkflow(); showMessage(result.message, 'success');
    $('#comparison-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { showMessage(error.message, 'error'); }
  finally { setLoading('restore-loading', false); restoreButton.disabled = !state.noisyUrl; }
});

downloadButton.addEventListener('click', () => {
  const filter = downloadButton.dataset.filter || 'adaptive';
  const url = state.download[filter];
  if (!url) { showMessage('Run a filter before downloading a restored image.', 'error'); return; }
  window.location.href = url;
});

// A new upload is only committed on successful upload; selecting a different file
// keeps the previous workflow usable until the new upload completes.
updateFilterSelection(); updateWorkflow();
