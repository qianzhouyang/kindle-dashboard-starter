'use strict';
(() => {
  const get = id => document.getElementById(id);
  const choices = new Map();
  let selected = null;
  let ready = false;
  let working = false;
  let previewVersion = 0;

  function status(message, error = false) {
    get('mockupStatus').textContent = message;
    get('mockupStatus').classList.toggle('error', error);
  }
  function controls() {
    get('mockupChoice').disabled = working || !choices.size;
    get('mockupUpload').disabled = working;
    get('mockupRotation').disabled = working || !selected || selected.width < selected.height;
    get('mockupPush').disabled = working || !ready;
    get('mockupRestore').disabled = working;
  }
  window.addEventListener('kindle-device-busy', event => { working = event.detail; controls(); });

  async function selectMockup(id) {
    const item = choices.get(id);
    if (!item) return;
    selected = item; ready = false; controls();
    const version = ++previewVersion;
    get('mockupDimensions').textContent = `${item.width} × ${item.height} · ` +
      (item.width > item.height ? '横屏推送时旋转为 1072 × 1448' : '竖屏原尺寸推送，不旋转');
    get('mockupCaption').textContent = `${item.name} · ${item.category}`;
    get('mockupPreview').hidden = true;
    status('正在加载整屏预览…');
    try {
      const image = new Image();
      image.src = '/api/mockup-preview?id=' + encodeURIComponent(item.id);
      await image.decode();
      if (version !== previewVersion) return;
      get('mockupPreview').src = image.src;
      get('mockupPreview').hidden = false;
      get('mockupPreview').classList.toggle('portrait', item.width < item.height);
      ready = true;
      status('预览已就绪。点击“推送这张图 · USB”查看实机效果。');
    } catch (error) {
      if (version === previewVersion) status('图片加载失败，请重新选择。上传图片需符合整屏尺寸。', true);
    } finally { if (version === previewVersion) controls(); }
  }

  async function pushMockup() {
    if (!selected || !ready || working) return;
    const item = selected;
    const rotation = Number(get('mockupRotation').value);
    busy(true); status(`正在通过 USB 推送「${item.name}」…请等待刷屏完成。`);
    try {
      const response = await fetch('/api/push-mockup', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: item.id, rotation})});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || result.message || '推送失败');
      status(result.message);
    } catch (error) { status(error.message || '推送失败，请检查 USB 连接后重试。', true); }
    finally { busy(false); loadStatus().catch(() => {}); }
  }

  async function uploadMockup(file) {
    if (!file || working) return;
    if (file.size > 8 * 1024 * 1024) { status('图片最大为 8 MiB。', true); return; }
    busy(true); status('正在读取整屏图片…');
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('无法读取所选文件')); reader.readAsDataURL(file);
      });
      const image = new Image(); image.src = data; await image.decode();
      if (!((image.naturalWidth === 1448 && image.naturalHeight === 1072) ||
            (image.naturalWidth === 1072 && image.naturalHeight === 1448))) {
        throw new Error('请上传 1448×1072 横屏或 1072×1448 竖屏图片；不会拉伸或裁切。');
      }
      const response = await fetch('/api/upload-image', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({data})});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || '上传失败');
      const item = {id: result.id, name: file.name, category: '自选整屏图', width: result.width, height: result.height};
      choices.set(item.id, item);
      get('mockupChoice').append(new Option('上传 · ' + file.name, item.id));
      get('mockupChoice').value = item.id;
      await selectMockup(item.id);
    } catch (error) { status(error.message || '图片读取失败', true); }
    finally { get('mockupUpload').value = ''; busy(false); }
  }

  get('mockupChoice').onchange = event => selectMockup(event.target.value);
  get('mockupUpload').onchange = event => uploadMockup(event.target.files[0]);
  get('mockupPush').onclick = pushMockup;
  get('mockupRestore').onclick = async () => {
    busy(true); status('正在恢复阅读界面…');
    try {
      const response = await fetch('/api/restore_kindle', {method: 'POST'});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || result.message || '恢复失败');
      status(result.message);
    } catch (error) { status(error.message, true); }
    finally { busy(false); loadStatus().catch(() => {}); }
  };
  fetch('/api/mockups').then(async response => {
    if (!response.ok) throw new Error('无法读取 mockup 列表');
    const library = await response.json();
    get('mockupChoice').replaceChildren();
    for (const item of library.items) {
      choices.set(item.id, item);
      get('mockupChoice').append(new Option(item.name + ' / ' + item.category, item.id));
    }
    get('mockupChoice').value = library.default_id;
    await selectMockup(library.default_id);
  }).catch(error => status(error.message, true));
})();
