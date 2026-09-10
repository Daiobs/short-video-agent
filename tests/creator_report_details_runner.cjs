const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const context = {console, currentCreatorIntelligenceStrategy: {templates: [{name: 'UNRELATED_REPORT'}], idea_bank: [{title: 'UNRELATED_IDEA'}]}};
context.window = context;
for (const name of ['escapeHtml','formatNumber','normalizeItems','creatorStrategyFromResult','qualityLabelFromScore','formatReportValue','cleanPublicReportText','reportItemPrimaryText','isMeaningfulReportText','renderPublicList','publicValueHasContent','renderPublicFields','renderPublicCard','renderSegmentSampleList','renderProfileSegments','segmentListCount','renderCompactPerformanceSegments','renderCreatorCloneEvidenceOverview','renderFormulaCards','renderTopicBuckets','compactReportList']) {
  const match = source.match(new RegExp('^function '+name+'\\([\\s\\S]*?^}', 'm'));
  if (!match) throw Error(name);
  vm.runInNewContext(match[0], context);
}
vm.runInNewContext(fs.readFileSync('app/static/modules/creator-report-view.js', 'utf8'), context);
const result = JSON.parse(fs.readFileSync(0, 'utf8'));
const container = {innerHTML: '', querySelector() {return this.innerHTML.includes('creator-distillation-report') ? {} : null;}};
const renderer = context.CreatorReportView.createRenderer(context);
renderer.render({container, result, overview: result.sample_overview || {}, viewModel: result.creator_report_view_model || {}});
process.stdout.write(container.innerHTML);
