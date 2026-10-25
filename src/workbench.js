'use strict';
let curTemplate = 'cat_office';
let draft = null;
let schema = null;
let selectedRegion = null;
let previewTimer = null;
let previewRequest = null;
let previewVersion = 0;
let previewURL = null;
let dirty = false;
const $ = id => document.getElementById(id);

function notify(message, type = 'success') {
  const element = $('toast');
  element.className = 'toast ' + type;
  element.style.display = 'block';
  element.textContent = message;
}
function markDirty(value = true) {
  dirty = value;
  $('saveState').textContent = value ? '有未保存的修改' : '当前配置已保存';
  $('saveState').classList.toggle('dirty', value);
}
function currentConfig() {
  const value = structuredClone(draft);
  value.template = curTemplate;
  value.quota = Number($('quotaInput').value);
  value.quote = $('quoteInput').value;
  value.rotation = Number($('rotationInput').value);
  value.frontlight = Number($('frontlightInput').value);
  value.city = $('cityInput').value;
  value.weather = {mode: $('weatherMode').value, latitude: $('latitudeInput').value === '' ? null : Number($('latitudeInput').value), longitude: $('longitudeInput').value === '' ? null : Number($('longitudeInput').value)};
  delete value.last_published;
  return value;
}
function regions() { return schema.layouts[curTemplate].regions; }
function region() { return regions().find(item => item.id === selectedRegion); }
function moduleValue() {
  return draft.customizations[curTemplate]?.[selectedRegion] || {type: 'inherit', title: '', text: '', value: '', font_size: 32, align: 'left', fit: 'contain', image_id: ''};
}
function setTemplate(template) {
  if (!draft) return;
  if (template !== curTemplate) markDirty();
  curTemplate = template;
  selectedRegion = regions()[0].id;
  document.querySelectorAll('.template-btn').forEach(button => button.classList.toggle('active', button.dataset.template === template));
  renderRegions(); renderEditor(); refreshPreview();
}
function selectRegion(id) {
  selectedRegion = id;
  renderRegions(); renderEditor();
}
function renderRegions() {
  const list = $('regionList'); const overlays = $('regionOverlay');
  list.replaceChildren(); overlays.replaceChildren();
  const layout = schema.layouts[curTemplate];
  $('kindleScreen').style.aspectRatio = layout.size.join(' / ');
  $('kindleFrame').classList.toggle('portrait', curTemplate === 'cluster');
  $('canvasSize').textContent = layout.size.join(' × ') + ' · ' + (curTemplate === 'cluster' ? '竖屏' : '横屏');
  for (const item of layout.regions) {
    const kind = draft.customizations[curTemplate]?.[item.id]?.type || 'inherit';
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'region-choice';
    button.classList.toggle('active', item.id === selectedRegion);
    button.classList.toggle('customized', kind !== 'inherit');
    button.textContent = item.name;
    const detail = document.createElement('small'); detail.textContent = schema.types[kind]; button.append(detail);
    button.onclick = () => selectRegion(item.id); list.append(button);
    const hit = document.createElement('button'); hit.type = 'button';
    hit.className = 'region-hit' + (item.id === selectedRegion ? ' selected' : '');
    hit.setAttribute('aria-label', '选择区域：' + item.name);
    const [x0, y0, x1, y1] = item.box;
    Object.assign(hit.style, {left: x0 / layout.size[0] * 100 + '%', top: y0 / layout.size[1] * 100 + '%',
      width: (x1 - x0) / layout.size[0] * 100 + '%', height: (y1 - y0) / layout.size[1] * 100 + '%'});
    const label = document.createElement('span'); label.textContent = item.name; hit.append(label);
    hit.onclick = () => { selectRegion(item.id); $('moduleEditor').scrollIntoView({block: 'nearest', behavior: 'smooth'}); };
    overlays.append(hit);
  }
  $('selectedRegionLabel').textContent = '正在编辑：' + region().name;
}
function visible(id, show) { $(id).hidden = !show; }
function renderEditor() {
  if (!selectedRegion) return;
  const value = moduleValue(); const kind = value.type;
  $('editorRegionName').textContent = region().name;
  $('moduleType').replaceChildren(...region().types.map(type => new Option(schema.types[type], type)));
  $('moduleType').value = kind;
  $('moduleTitle').value = value.title || '';
  $('moduleText').value = value.text || '';
  $('moduleValue').value = value.value || '';
  $('moduleFont').value = value.font_size || 32;
  $('moduleFontValue').textContent = (value.font_size || 32) + ' px';
  $('moduleAlign').value = value.align || 'left';
  $('imageFit').value = value.fit || 'contain';
  visible('inheritHelp', kind === 'inherit');
  visible('titleField', !['inherit', 'blank'].includes(kind));
  visible('textField', ['text', 'clock', 'metric', 'quota'].includes(kind));
  visible('valueField', ['metric', 'quota'].includes(kind));
  visible('imageField', kind === 'image');
  visible('formatFields', !['inherit', 'blank', 'calendar'].includes(kind));
  $('moduleValueLabel').textContent = kind === 'quota' ? '进度值（0–100；留空跟随全局额度）' : '数值或重点文字';
  $('moduleTextLabel').textContent = kind === 'clock' ? '日期说明（留空显示日期与星期）' : '内容 / 补充说明';
  $('moduleValue').placeholder = kind === 'quota' ? '例如：75' : '例如：本周完成 5 件';
  $('textCount').textContent = (value.text || '').length + ' / 2000';
  const imageId = value.image_id || 'builtin:cat';
  $('imageChoice').replaceChildren(new Option('工作猫 · 竖幅', 'builtin:cat'), new Option('工作猫 · 宽幅', 'builtin:work'), new Option('休息猫 · 宽幅', 'builtin:home'));
  if (!imageId.startsWith('builtin:')) $('imageChoice').append(new Option('已上传的图片', imageId));
  $('imageChoice').value = imageId;
  $('imageThumb').src = imageId.startsWith('builtin:') ? '/api/builtin-' + imageId.split(':')[1] + '.png' : '/api/assets/' + imageId;
}
function setModule(field, value) {
  if (!draft) return;
  const current = {...moduleValue(), [field]: value};
  if (field === 'type' && value === 'image' && !current.image_id) current.image_id = 'builtin:cat';
  draft.customizations[curTemplate] ||= {};
  if (current.type === 'inherit') delete draft.customizations[curTemplate][selectedRegion];
  else draft.customizations[curTemplate][selectedRegion] = current;
  markDirty(); renderRegions();
  if (['type', 'image_id'].includes(field)) renderEditor();
  if (field === 'text') $('textCount').textContent = value.length + ' / 2000';
  if (field === 'font_size') $('moduleFontValue').textContent = value + ' px';
  schedulePreview();
}
function resetRegion() { setModule('type', 'inherit'); }
function resetTemplate() {
  draft.customizations[curTemplate] = {};
  markDirty(); renderRegions(); renderEditor(); refreshPreview();
}
function insertToken(token) {
  const field = $('moduleText');
  field.setRangeText(token, field.selectionStart, field.selectionEnd, 'end');
  setModule('text', field.value); field.focus();
}
function editGlobal() {
  if (!draft) return;
  updateQuotaVal($('quotaInput').value); markDirty(); schedulePreview();
}
function updateQuotaVal(value) { $('quotaVal').textContent = value + '%'; }
function setQuote(text) { $('quoteInput').value = text; editGlobal(); }
function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(refreshPreview, 350); }
async function refreshPreview() {
  if (!draft) return;
  clearTimeout(previewTimer); previewRequest?.abort();
  previewRequest = new AbortController(); const version = ++previewVersion;
  $('previewLoading').style.display = 'flex';
  $('kindleFrame').classList.toggle('logo-left', $('rotationInput').value === '90');
  try {
    const response = await fetch('/api/preview', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(currentConfig()), signal: previewRequest.signal});
    if (!response.ok) throw new Error((await response.json()).error || '预览生成失败');
    const blob = await response.blob(); if (version !== previewVersion) return;
    const old = previewURL; previewURL = URL.createObjectURL(blob); $('previewImg').src = previewURL;
    if (old) URL.revokeObjectURL(old);
    $('previewStatus').textContent = '预览已更新 · ' + new Date().toLocaleTimeString();
  } catch (error) {
    if (error.name !== 'AbortError') { notify(error.message, 'error'); $('previewStatus').textContent = '预览未更新，请检查配置'; }
  } finally { if (version === previewVersion) $('previewLoading').style.display = 'none'; }
}
async function uploadImage(file) {
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) { notify('图片最大为 8 MiB', 'error'); return; }
  const targetTemplate = curTemplate; const targetRegion = selectedRegion;
  $('uploadStatus').textContent = '正在处理图片…';
  try {
    const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
    const response = await fetch('/api/upload-image', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({data: encoded})});
    const result = await response.json(); if (!response.ok || !result.ok) throw new Error(result.error || '上传失败');
    draft.customizations[targetTemplate] ||= {};
    const old = draft.customizations[targetTemplate][targetRegion] || {};
    draft.customizations[targetTemplate][targetRegion] = {...old, type: 'image', image_id: result.id};
    markDirty(); renderRegions(); renderEditor(); refreshPreview();
    $('uploadStatus').textContent = `图片已就绪：${result.width} × ${result.height}`;
  } catch (error) { $('uploadStatus').textContent = ''; notify(error.message || '图片读取失败', 'error'); }
  $('imageUpload').value = '';
}
function busy(value) {
  document.querySelectorAll('.actions button').forEach(button => button.disabled = value);
  window.dispatchEvent(new CustomEvent('kindle-device-busy', {detail: value}));
}
async function saveOrPush(push) {
  const config = currentConfig(); const snapshot = JSON.stringify(config); busy(true);
  notify(push ? '正在保存并推送到 Kindle…' : '正在保存配置并生成发布画面…');
  try {
    const response = await fetch(push ? '/api/push_now' : '/api/publish', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config)});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || result.message || '保存失败');
    if (JSON.stringify(currentConfig()) === snapshot) markDirty(false);
    notify(push ? result.message : '已保存并发布。Kindle 下次联网刷新会取得这份配置。');
    await loadStatus();
  } catch (error) { notify(error.message, 'error'); }
  finally { busy(false); }
}
function publishConfig() { return saveOrPush(false); }
function pushNow() { return saveOrPush(true); }
async function restoreKindle() {
  busy(true); notify('正在恢复原生阅读界面…');
  try {
    const response = await fetch('/api/restore_kindle', {method: 'POST'}); const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || result.message || '恢复失败');
    notify(result.message); await loadStatus();
  } catch (error) { notify(error.message, 'error'); }
  finally { busy(false); }
}
async function loadStatus() {
  try {
    const response = await fetch('/api/status'); const status = await response.json();
    $('connStatus').replaceChildren();
    const dot = document.createElement('span'); dot.className = 'status-dot' + (status.online ? ' online' : '');
    $('connStatus').append(dot, document.createTextNode(status.online ? ' USB SSH 在线' : ' Kindle 脱机 / 待机中'));
    $('lastPublishedTime').textContent = '上次发布：' + (status.last_published || '尚未发布');
    return status;
  } catch (error) { $('connStatus').textContent = '连接工作台失败'; throw error; }
}
async function initialize() {
  try {
    const [definition, status] = await Promise.all([fetch('/api/module-schema').then(r => r.json()), loadStatus()]);
    schema = definition; draft = structuredClone(status.config); draft.customizations ||= {};
    $('cityInput').value = draft.city; $('weatherMode').value = draft.weather.mode;
    $('latitudeInput').value = draft.weather.latitude ?? ''; $('longitudeInput').value = draft.weather.longitude ?? '';
    $('quotaInput').value = draft.quota; updateQuotaVal(draft.quota);
    $('quoteInput').value = draft.quote; $('rotationInput').value = draft.rotation;
    $('frontlightInput').replaceChildren(...Array.from({length: 25}, (_, level) =>
      new Option(level === 0 ? '0 · 关闭' : level + ' / 24', String(level))));
    $('frontlightInput').value = draft.frontlight;
    for (const token of schema.tokens) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = token; button.onclick = () => insertToken(token); $('tokenButtons').append(button);
    }
    curTemplate = draft.template; setTemplate(curTemplate); markDirty(false);
    $('regionOverlayToggle').onchange = () => $('regionOverlay').classList.toggle('hidden', !$('regionOverlayToggle').checked);
    setInterval(() => loadStatus().catch(() => {}), 15000);
    window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  } catch (error) { notify('工作台初始化失败：' + error.message, 'error'); }
}
initialize();
