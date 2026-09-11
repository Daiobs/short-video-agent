const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname, '../app/static', file), 'utf8');
const document = {readyState: 'complete', querySelector() { return null; }};
const window = {document, location: {origin: 'http://localhost:9999'}};
const context = {window, global: window, URL, URLSearchParams};
vm.runInNewContext(read('library.js'), context);
const app = read('app.js');
vm.runInNewContext(app.match(/^function safeWorkbenchInternalUrl\([\s\S]*?^}/m)[0], context);
vm.runInNewContext(read('workbench-tasks.js').match(/^  function normalizeOpenUrl\([\s\S]*?^  }/m)[0], context);
const base = '/api/creator-clone/sets/clone_' + 'a'.repeat(32) + '/files/creator_clone';
for (const safe of [window.LibraryPage.safeOpenUrl, context.safeWorkbenchInternalUrl, context.normalizeOpenUrl]) {
  for (const suffix of ['.html', '.html?view=1', '.md']) {
    assert.equal(safe(base + suffix), base + (suffix === '.html' ? '.html?view=1' : suffix));
  }
  assert.equal(safe('/cases/case_abc'), '/cases/case_abc');
  for (const suffix of ['.md?view=1', '.html?view=0', '.html?view=true', '.html?view=01',
    '.html?view=1&x=2', '.html?view=1&view=1', '.html?view=%31', '.html?%76iew=1',
    '.html?view=1#bad', '.html?x=1', '.json?view=1']) {
    assert.equal(safe(base + suffix), '', suffix);
  }
  assert.equal(safe('/cases/case_abc?view=1'), '');
  assert.equal(safe('https://evil.example' + base + '.html?view=1'), '');
}
class Node {
  constructor(tag, ownerDocument) {
    Object.assign(this, {tag, ownerDocument, children: [], dataset: {}, listeners: {}});
  }
  appendChild(node) { this.children.push(node); }
  addEventListener(event, callback) { this.listeners[event] = callback; }
}
const fakeDocument = {createElement(tag) { return new Node(tag, fakeDocument); }};
const descendants = node => [node, ...node.children.flatMap(descendants)];
const returns = [];
function row(url) {
  return descendants(window.LibraryPage.renderAssetRow(fakeDocument, {
    asset_type: 'creator_report', open_url: url,
    resume_target: {route: 'profile', resource_id: 'clone_' + 'a'.repeat(32), stage: 'export', open_url: url},
  }, target => returns.push(target)));
}
for (const url of [base + '.html', base + '.html?view=1']) {
  const nodes = row(url);
  const links = nodes.filter(node => node.tag === 'a');
  assert.equal(links.length, 2);
  assert.equal(links[0].textContent, '打开报告');
  assert.equal(links[0].href, base + '.html?view=1');
  assert.equal(links[0].target, '_blank');
  assert.equal(links[0].rel, 'noopener noreferrer');
  assert.equal(links[0].download, undefined);
  assert.equal(links[1].textContent, '下载 HTML');
  assert.equal(links[1].href, base + '.html');
  nodes.find(node => node.tag === 'button').listeners.click();
  assert.equal(returns.at(-1).route, 'profile');
  assert.equal(returns.at(-1).stage, 'export');
  assert.equal(returns.at(-1).open_url, base + '.html?view=1');
}
const markdown = row(base + '.md').filter(node => node.tag === 'a');
assert.equal(markdown.length, 1);
assert.equal(markdown[0].textContent, '下载 Markdown');
assert.equal(markdown[0].href, base + '.md');
assert.equal(row('https://evil.example/report').filter(node => node.tag === 'a').length, 0);
// Execute the existing Creator link update block without mounting its report renderer.
const creatorBlock = app.match(/  if \(downloadCreatorCloneMd && set\?\.set_id\) \{[\s\S]*?\n  }/)[0];
for (const html of [true, false]) {
  const link = {};
  vm.runInNewContext(creatorBlock, {
    downloadCreatorCloneMd: link, set: {set_id: 'clone_' + 'a'.repeat(32)},
    exports: {creator_clone_html: html}, encodeURIComponent,
  });
  assert.equal(link.href, base + (html ? '.html?view=1' : '.md'));
  assert.equal(link.textContent, html ? '打开网页报告' : '下载 Markdown');
}
async function testWizardDownload() {
  const handler = app.match(/^async function handleWizardPrimaryAction\([\s\S]*?^}/m)[0];
  for (const suffix of ['.html?view=1', '.html', '.md', '.html?view=10', '.html?view=1&other=1']) {
    for (const restore of [false, true]) {
      let href = restore ? '#' : base + suffix;
      const opened = [];
      let hydrated = 0;
      const sandbox = {
        creatorCloneNextButton: {dataset: {creatorCloneAction: 'export_report'}},
        downloadCreatorCloneMd: {getAttribute() { return href; }},
        currentCreatorCloneSetId() { return 'clone_' + 'a'.repeat(32); },
        async hydrateCreatorCloneReportFromSet() { hydrated++; href = base + suffix; },
        window: {open(...args) { opened.push(args); }},
      };
      vm.runInNewContext(handler, sandbox);
      await sandbox.handleWizardPrimaryAction();
      assert.deepEqual(opened, [[base + (suffix === '.html?view=1' ? '.html' : suffix), '_blank', 'noopener,noreferrer']]);
      assert.equal(hydrated, Number(restore));
      assert.equal(href, base + suffix, 'Opening link must remain unchanged');
    }
  }
}
testWizardDownload().then(() => {
  console.log('library report inline frontend behavior: passed');
}).catch(error => { console.error(error); process.exitCode = 1; });
