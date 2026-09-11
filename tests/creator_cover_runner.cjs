const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
const requests = [];
const cached = new Map();
class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.events = {};
    this.complete = false;
    this.naturalWidth = 0;
  }
  set src(value) {
    this.url = value;
    requests.push(value);
    this.complete = cached.has(value);
    this.naturalWidth = cached.get(value) || 0;
  }
  get src() { return this.url; }
  appendChild(child) { child.parentNode = this; this.children.push(child); }
  replaceWith(child) {
    const parent = this.parentNode;
    assert.ok(parent);
    parent.children[parent.children.indexOf(this)] = child;
    child.parentNode = parent;
    this.parentNode = null;
  }
  contains(child) { return this === child || this.children.some(node => node.contains(child)); }
  querySelectorAll() {
    return this.children.flatMap(child => child.tag === 'img' ? [child] : child.querySelectorAll());
  }
  addEventListener(type, callback, options) {
    (this.events[type] ||= []).push({callback, once: options?.once});
  }
  emit(type, width = 0) {
    this.naturalWidth = width;
    const events = this.events[type] || [];
    this.events[type] = events.filter(event => !event.once);
    events.forEach(event => event.callback());
  }
}
const body = new Element('tbody');
const context = {
  document: {createElement: tag => new Element(tag)}, profileResultsBody: body,
  currentCreatorIntelligenceProject: null, runtimeSampleRows: [],
  syncCreatorProjectSamplesFromViewItems() {}, renderProfileTable() {},
};
for (const name of ['escapeHtml', 'normalizeItems', 'sampleViewItemKey', 'sampleViewItemMatchesKeySet',
  'sampleViewItemFromCreatorSample', 'creatorSampleFromViewItem', 'creatorProjectSampleViewItems',
  'activeCreatorSampleViewItems', 'mergeProfileQueueItems', 'safeProfilePreviewUrl',
  'profileCoverMarkup', 'profileCoverFallbackLabel', 'profileCoverFallbackMarkup',
  'installProfileCoverFallbacks', 'bindProfileCover']) {
  const match = source.match(new RegExp('^function ' + name + '\\([\\s\\S]*?^}', 'm'));
  assert.ok(match, name);
  vm.runInNewContext(match[0], context);
}
const item = {sample_id: 's1', case_id: 'case_1', title: 'Title <one>', media_type: 'video',
  cover_url: 'https://cdn.example/cover.jpg', preview_url: '/api/cases/case_1/keyframes/001.jpg', preview_source: 'video_frame'};
function mount(items) {
  body.children.forEach(child => { child.parentNode = null; });
  body.children = [];
  return items.map(value => {
    const markup = context.profileCoverMarkup(value);
    if (!markup.includes('<img ')) return null;
    const slot = new Element('span');
    const img = new Element('img');
    img.alt = value.title;
    img.dataset.profilePreviewUrl = context.safeProfilePreviewUrl(value);
    img.dataset.profileCoverLocal = String(!value.cover_url);
    img.dataset.profileCoverFallback = context.profileCoverFallbackLabel(value);
    img.src = value.cover_url || img.dataset.profilePreviewUrl;
    slot.appendChild(img);
    body.appendChild(slot);
    return img;
  });
}
function bind() { context.installProfileCoverFallbacks(); }
let [remote] = mount([item]);
bind(); bind();
assert.equal(remote.events.error.length, 1);
remote.emit('load', 68);
remote.emit('error');
assert.deepEqual(requests, [item.cover_url]);
assert.match(context.profileCoverMarkup(item), /alt="Title &lt;one&gt;"/);
assert.match(context.profileCoverMarkup(item), /referrerpolicy="no-referrer"/);
[remote] = mount([item]); bind(); remote.emit('error');
let local = body.querySelectorAll()[0];
assert.equal(local.src, item.preview_url);
assert.equal(local.alt, item.title);
assert.equal(local.referrerPolicy, 'no-referrer');
assert.equal(local.parentNode.children[1].textContent, '视频帧预览');
remote.emit('load', 68); remote.emit('error');
assert.equal(body.querySelectorAll()[0], local);
local.emit('error');
assert.equal(body.querySelectorAll().length, 0);
assert.match(body.children[0].innerHTML, /暂无可用预览/);
const count = requests.length;
local.emit('error'); bind();
assert.equal(requests.length, count);
cached.set(item.cover_url, 0);
[remote] = mount([item]); bind();
assert.equal(body.querySelectorAll()[0].src, item.preview_url);
cached.set(item.preview_url, 0);
mount([item]); bind();
assert.equal(body.querySelectorAll().length, 0);
cached.set(item.cover_url, 68);
mount([item]); const before = requests.length; bind();
assert.equal(requests.length, before);
cached.clear();
const localOnly = {...item, cover_url: ''};
assert.match(context.profileCoverMarkup(localOnly), /视频帧预览/);
mount([localOnly]); bind();
assert.equal(body.querySelectorAll()[0].src, item.preview_url);
body.querySelectorAll()[0].emit('load', 68);
assert.equal(body.querySelectorAll().length, 1);
// Reorder/re-render rows while old requests are still pending.
const other = {...item, sample_id: 's2', case_id: 'case_2', cover_url: 'https://cdn.example/two.jpg',
  preview_url: '/api/cases/case_2/keyframes/002.jpg'};
const old = mount([item, other]); bind();
const fresh = mount([other, item]); bind();
const beforeLate = requests.length;
old[0].emit('error'); old[1].emit('load', 68);
assert.equal(requests.length, beforeLate);
assert.deepEqual(body.querySelectorAll(), fresh);
fresh[0].emit('error'); fresh[1].emit('load', 68);
assert.equal(body.querySelectorAll()[0].src, other.preview_url);
assert.equal(body.querySelectorAll()[1].src, item.cover_url);
for (const url of ['https://evil/a', '//evil/a', '/api/cases/case_2/keyframes/001.jpg',
  '/api/cases/case_1/keyframes/../secret', '/api/cases/case_1/keyframes/%2e%2e',
  '/api/cases/case_1/keyframes/a%2fb.jpg', '/api/cases/case_1/keyframes/a.jpg?x=1',
  '/api/cases/case_1/keyframes/a.jpg#x', '/api/cases/case_1/keyframes/a\\b.jpg',
  '/api/cases/case_1/keyframes/a.jpg\n']) {
  assert.equal(context.safeProfilePreviewUrl({...item, preview_url: url}), '', url);
  assert.ok(!context.profileCoverMarkup({...localOnly, preview_url: url}).includes('<img'));
}
assert.equal(context.safeProfilePreviewUrl({...item, preview_source: ''}), '');
const dto = context.creatorSampleFromViewItem(item);
const roundTrip = context.sampleViewItemFromCreatorSample(dto);
for (const key of ['cover_url', 'preview_url', 'preview_source']) assert.equal(roundTrip[key], item[key]);
assert.equal(context.sampleViewItemFromCreatorSample({raw: item}).preview_url, item.preview_url);
assert.equal(context.sampleViewItemFromCreatorSample({...dto, preview_url: ''}).preview_url, '');
context.currentCreatorIntelligenceProject = {samples: [dto]};
context.runtimeSampleRows = [{sample_id: 's1', title: 'updated'}];
assert.equal(context.activeCreatorSampleViewItems()[0].preview_url, item.preview_url);
context.mergeProfileQueueItems([{sample_id: 's1', preview_url: '/api/cases/case_1/keyframes/003.jpg', preview_source: 'video_frame'}]);
assert.equal(context.runtimeSampleRows[0].preview_url, '/api/cases/case_1/keyframes/003.jpg');
assert.equal(context.runtimeSampleRows[0].preview_source, 'video_frame');
assert.equal(context.runtimeSampleRows[0].cover_url, item.cover_url);
console.log('creator cover frontend behavior: passed');
