'use strict';
/*
 * Checks an exported n8n workflow without starting n8n:
 *   1. structure: node types and versions exist, connections are valid, everything is reachable,
 *      the "valid" / "problem" branches are not swapped, no API key is typed into a node;
 *   2. parameters: every parameter name exists in the node definition of the pinned n8n version;
 *   3. expressions: the key expressions are evaluated by n8n's own expression engine on sample data.
 *
 * Usage:  node validate_workflow.js [workflows/invoice_pipeline.json]
 */
const fs = require('fs');
const path = require('path');
const { Workflow, NodeHelpers } = require('n8n-workflow');

const NODES_DIR = path.dirname(require.resolve('n8n-nodes-base/package.json'));
const MANIFEST = require('n8n-nodes-base/package.json').n8n.nodes;
const SKIP_DEEP_CHECK = new Set(['resourceMapper', 'resourceLocator']); // shaped by the n8n editor

// 'dist/nodes/HttpRequest/HttpRequest.node.js' -> 'httpRequest'
const fileByType = {};
for (const file of MANIFEST) {
  const base = path.basename(file, '.node.js');
  fileByType[base.charAt(0).toLowerCase() + base.slice(1)] = file;
}
const cache = {};
function nodeInstance(typeName) {
  const short = typeName.replace('n8n-nodes-base.', '');
  if (!typeName.startsWith('n8n-nodes-base.') || !fileByType[short]) return null;
  if (!cache[short]) {
    const mod = require(path.join(NODES_DIR, fileByType[short]));
    const Cls = Object.values(mod).find((v) => typeof v === 'function');
    cache[short] = new Cls();
  }
  return cache[short];
}
const nodeTypes = {
  getByName(name) { return this.getByNameAndVersion(name); },
  getByNameAndVersion(name, version) {
    const inst = nodeInstance(name);
    if (!inst) throw new Error(`unknown node type ${name}`);
    return NodeHelpers.getVersionedNodeType(inst, version);
  },
  getKnownTypes() { return {}; },
};

// ---------------------------------------------------------------- setup
const file = process.argv[2] || 'workflows/invoice_pipeline.json';
// `raw` is never touched: the Workflow constructor normalises (= changes) the nodes it receives
const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
const wf = JSON.parse(JSON.stringify(raw));
let problems = 0;
const bad = (message) => { problems += 1; console.log('  PROBLEM:', message); };
const nodeNamed = (name) => raw.nodes.find((n) => n.name === name);
const short = (t) => t.replace('n8n-nodes-base.', '');

// ---------------------------------------------------------------- 1. structure
console.log(`== 1. structure of ${file}`);
const names = raw.nodes.map((n) => n.name);
if (new Set(names).size !== names.length) bad('node names are not unique');
const known = [];
for (const n of raw.nodes) {
  const inst = nodeInstance(n.type);
  if (!inst) { bad(`${n.name}: unknown node type ${n.type}`); continue; }
  known.push(n);
  const versions = inst.nodeVersions ? Object.keys(inst.nodeVersions).map(Number) : [].concat(inst.description.version);
  if (!versions.includes(n.typeVersion)) bad(`${n.name}: typeVersion ${n.typeVersion} does not exist (available: ${versions.join(', ')})`);
}
for (const [from, outputs] of Object.entries(raw.connections)) {
  if (!names.includes(from)) bad(`connection starts at unknown node "${from}"`);
  for (const group of outputs.main || []) for (const c of group) if (!names.includes(c.node)) bad(`connection points to unknown node "${c.node}"`);
}
const webhook = raw.nodes.find((n) => n.type === 'n8n-nodes-base.webhook');
if (!webhook) bad('there is no webhook node');
else {
  const reach = new Set([webhook.name]);
  const queue = [webhook.name];
  while (queue.length) {
    const cur = queue.shift();
    for (const group of raw.connections[cur]?.main || []) for (const c of group) if (!reach.has(c.node)) { reach.add(c.node); queue.push(c.node); }
  }
  for (const n of raw.nodes) if (n.type !== 'n8n-nodes-base.stickyNote' && !reach.has(n.name)) bad(`"${n.name}" cannot be reached from the webhook`);
}
const branch = (name, output) => (raw.connections[name]?.main?.[output] || []).map((c) => c.node);
if (!branch('Is the invoice valid?', 0).includes('Prepare answer: processed')) bad('the TRUE output of "Is the invoice valid?" must lead to "Prepare answer: processed"');
if (!branch('Is the invoice valid?', 1).includes('Email: invoice needs review')) bad('the FALSE output of "Is the invoice valid?" must lead to "Email: invoice needs review"');
for (const n of raw.nodes.filter((x) => x.type === 'n8n-nodes-base.httpRequest')) {
  for (const h of n.parameters?.headerParameters?.parameters || []) {
    if (/api[-_ ]?key|authorization/i.test(h.name || '')) bad(`${n.name}: the header "${h.name}" is typed into the node. Use a credential instead`);
  }
}
console.log(`  ${raw.nodes.length} nodes, ${Object.keys(raw.connections).length} nodes with outgoing connections`);

// ---------------------------------------------------------------- 2. parameters
console.log(`== 2. parameters vs node definitions (n8n-nodes-base ${require('n8n-nodes-base/package.json').version})`);
const flat = (o, p = '') => (o !== null && typeof o === 'object'
  ? Object.entries(o).flatMap(([k, v]) => flat(v, p ? `${p}.${k}` : k))
  : [[p, o]]);
const workflow = new Workflow({ id: 'wf', name: wf.name, nodes: wf.nodes.filter((n) => nodeInstance(n.type)), connections: wf.connections, active: false, nodeTypes, staticData: {}, settings: wf.settings });
for (const n of known) {
  const nt = nodeTypes.getByNameAndVersion(n.type, n.typeVersion);
  const props = nt.description.properties;
  const propByName = Object.fromEntries(props.map((p) => [p.name, p]));
  const unknownKeys = Object.keys(n.parameters || {}).filter((k) => !propByName[k]);
  const norm = NodeHelpers.getNodeParameters(props, n.parameters || {}, true, false, n, nt.description) || {};
  const have = new Map(flat(norm));
  const lost = [];
  for (const key of Object.keys(n.parameters || {}).filter((k) => propByName[k] && !SKIP_DEEP_CHECK.has(propByName[k].type))) {
    for (const [p, v] of flat(n.parameters[key], key)) {
      if (p.endsWith('.id')) continue;
      if (!have.has(p) || JSON.stringify(have.get(p)) !== JSON.stringify(v)) lost.push(p);
    }
  }
  if (unknownKeys.length) bad(`${n.name}: unknown parameter(s) ${unknownKeys.join(', ')}`);
  if (lost.length) bad(`${n.name}: parameter(s) the node ignores or changes: ${lost.join(', ')}`);
  console.log(`  ${unknownKeys.length || lost.length ? 'x ' : 'ok'}  ${n.name}  (${short(n.type)} v${n.typeVersion})`);
}

// ---------------------------------------------------------------- 3. expressions
console.log('== 3. key expressions on sample data');
const item = (json, binary) => ({ json, ...(binary ? { binary } : {}) });
const apiOk = { source: 'invoice_0001.pdf', valid: true, number: 'INV-2026-0001', vendor: 'Blue Harbor Trading', total: '84.24', warnings: [] };
const apiBad = { source: 'bad_total.pdf', valid: false, number: 'INV-10', vendor: 'Acme Parts', total: '99.00', warnings: ['Subtotal + tax is 22.60, but the total is 99.00'] };
const apiBroken = { source: 'broken.pdf', valid: false, number: null, vendor: null, total: null, warnings: ['Could not read PDF: No /Root object! - Is this really a PDF?'] };
const upload = { file0: { data: 'x', mimeType: 'application/pdf', fileName: 'invoice_0001.pdf' } };

function evaluate(nodeName, expression, inputItems, runData) {
  const runExecutionData = {
    startData: {},
    resultData: { runData: Object.fromEntries(Object.entries(runData).map(([k, items]) => [k, [{ startTime: 0, executionIndex: 0, executionTime: 0, source: [], data: { main: [items] } }]])) },
    executionData: { contextData: {}, nodeExecutionStack: [], metadata: {}, waitingExecution: {}, waitingExecutionSource: {} },
  };
  const node = wf.nodes.find((n) => n.name === nodeName);
  const executeData = { node, data: { main: [inputItems] }, source: { main: [{ previousNode: 'x' }] } };
  return workflow.expression.getParameterValue(expression, runExecutionData, 0, 0, nodeName, inputItems, 'manual', {}, executeData);
}
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad(`${label}: got ${JSON.stringify(got)}, expected ${JSON.stringify(want)}`);
  console.log(`  ${ok ? 'ok' : 'x '}  ${label}`);
}
function section(label, nodeNames, fn) {
  const missing = nodeNames.filter((name) => !nodeNamed(name));
  if (missing.length) { bad(`${label}: the workflow has no node named ${missing.map((m) => `"${m}"`).join(', ')} (rename it back or update this script)`); return; }
  try { fn(); } catch (e) { bad(`${label}: ${e.message}`); }
}
const params = (name) => nodeNamed(name).parameters;

section('upload field', ['Extract invoice data'], () => {
  const expr = params('Extract invoice data').bodyParameters.parameters[0].inputDataFieldName;
  check('the uploaded file is found when n8n names it "file0"', evaluate('Extract invoice data', expr, [item({}, upload)], { 'Receive invoice': [item({}, upload)] }), 'file0');
  check('the uploaded file is found when n8n names it "data"', evaluate('Extract invoice data', expr, [item({}, { data: upload.file0 })], { 'Receive invoice': [item({}, { data: upload.file0 })] }), 'data');
});
section('condition', ['Is the invoice valid?'], () => {
  const left = params('Is the invoice valid?').conditions.conditions[0].leftValue;
  check('a valid invoice goes to the TRUE branch', evaluate('Is the invoice valid?', left, [item(apiOk)], { 'Extract invoice data': [item(apiOk)] }), true);
  check('a problem invoice goes to the FALSE branch', evaluate('Is the invoice valid?', left, [item(apiBad)], { 'Extract invoice data': [item(apiBad)] }), false);
});
section('answer: processed', ['Prepare answer: processed'], () => {
  const asg = params('Prepare answer: processed').assignments.assignments;
  const got = Object.fromEntries(asg.map((a) => [a.name, String(a.value).startsWith('=') ? evaluate('Prepare answer: processed', a.value, [item(apiOk)], { 'Extract invoice data': [item(apiOk)] }) : a.value]));
  check('the "processed" answer', got, { status: 'processed', source: 'invoice_0001.pdf', number: 'INV-2026-0001', vendor: 'Blue Harbor Trading', total: '84.24' });
});
for (const [label, api] of [['wrong total', apiBad], ['unreadable file', apiBroken]]) {
  section(`e-mail (${label})`, ['Email: invoice needs review'], () => {
    const p = params('Email: invoice needs review');
    const runData = { 'Extract invoice data': [item(api)] };
    const subject = evaluate('Email: invoice needs review', p.subject, [item(api)], runData);
    const text = evaluate('Email: invoice needs review', p.text, [item(api)], runData);
    const ok = subject.includes(api.source) && text.includes(api.warnings[0]) && (api.number !== null || text.includes('not found'));
    if (!ok) bad(`e-mail (${label}) lacks the file name, the warning or the "not found" placeholders`);
    console.log(`  ${ok ? 'ok' : 'x '}  e-mail for ${label}: ${JSON.stringify(subject)}`);
  });
}
section('answer: needs review', ['Prepare answer: needs review', 'Email: invoice needs review'], () => {
  const asg = params('Prepare answer: needs review').assignments.assignments;
  const emailResult = [item({ messageId: '<x@pipeline.local>', accepted: ['accountant@pipeline.local'] })];
  const runData = { 'Extract invoice data': [item(apiBad)], 'Email: invoice needs review': emailResult };
  const got = Object.fromEntries(asg.map((a) => [a.name, String(a.value).startsWith('=') ? evaluate('Prepare answer: needs review', a.value, emailResult, runData) : a.value]));
  check('the "needs review" answer still has the invoice data (the input item is the e-mail result)', got, { status: 'needs_review', source: 'bad_total.pdf', warnings: ['Subtotal + tax is 22.60, but the total is 99.00'] });
});

console.log(problems ? `\nRESULT: ${problems} problem(s) found` : '\nRESULT: no problems found');
process.exit(problems ? 1 : 0);