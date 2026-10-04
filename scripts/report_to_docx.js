// Build a Word document from Markdown: the final report (docs/report/REPORT.md, with title page and contents) or
// a plain document such as docs/usability/KIT.md (one page per top-level heading).
// Not part of the app and not in requirements: run it from a scratch folder with its own node packages:
//   mkdir /tmp/r && cd /tmp/r && npm init -y && npm install docx@9 marked@14 image-size@1
//   NODE_PATH=/tmp/r/node_modules node /path/to/smartrest/scripts/report_to_docx.js \
//     docs/report/REPORT.md docs/report/SmartRestaurant_Final_Report_DRAFT.docx
// Text marked [TEAM: ...] is highlighted yellow. Open the result in Word and update the table of contents.
const fs = require('fs');
const path = require('path');
const { marked } = require('marked');
const sizeOf = require('image-size');
const D = require('docx');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  AlignmentType, HeadingLevel, TableOfContents, PageBreak, Footer, PageNumber, LevelFormat,
} = D;

const [, , SRC, OUT] = process.argv;
const BASE = path.dirname(SRC);
const PAGE_W = 11906, MARGIN = 1440, CONTENT_W = PAGE_W - 2 * MARGIN;   // A4, 1 inch margins (DXA)
const MAX_IMG_W = 600, MAX_IMG_H = 820;                                // pixels at 96 dpi
const FONT = 'Calibri', MONO = 'Consolas';

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'");

// ---- inline runs ----------------------------------------------------------------------------
function runs(tokens, fmt = {}) {
  const out = [];
  for (const t of tokens || []) {
    switch (t.type) {
      case 'strong': out.push(...runs(t.tokens, { ...fmt, bold: true })); break;
      case 'em': out.push(...runs(t.tokens, { ...fmt, italics: true })); break;
      case 'codespan': out.push(textRun(decode(t.text), { ...fmt, font: MONO, size: 19 })); break;
      case 'link': out.push(...runs(t.tokens, fmt)); break;
      case 'br': out.push(new TextRun({ break: 1 })); break;
      case 'escape': out.push(textRun(decode(t.text), fmt)); break;
      case 'del': out.push(...runs(t.tokens, { ...fmt, strike: true })); break;
      case 'text':
        if (t.tokens && t.tokens.length) out.push(...runs(t.tokens, fmt));
        else out.push(textRun(decode(t.text), fmt));
        break;
      case 'image': break; // handled at paragraph level
      default: if (t.text) out.push(textRun(decode(t.text), fmt));
    }
  }
  return out;
}
let inTeam = false;  // [TEAM: ...] markers are highlighted until the closing bracket
function textRun(text, fmt) {
  const parts = [];
  let rest = text;
  while (rest.length) {
    if (!inTeam) {
      const i = rest.indexOf('[TEAM');
      if (i < 0) { parts.push([rest, false]); break; }
      if (i > 0) parts.push([rest.slice(0, i), false]);
      rest = rest.slice(i); inTeam = true;
    } else {
      const j = rest.indexOf(']');
      if (j < 0) { parts.push([rest, true]); break; }
      parts.push([rest.slice(0, j + 1), true]); rest = rest.slice(j + 1); inTeam = false;
    }
  }
  if (parts.length === 1) return new TextRun({ text: parts[0][0], ...fmt, ...(parts[0][1] ? { highlight: 'yellow' } : {}) });
  return parts.map(([s, hl]) => new TextRun({ text: s, ...fmt, ...(hl ? { highlight: 'yellow' } : {}) }));
}
const flat = (a) => a.flat(Infinity);

// ---- blocks -----------------------------------------------------------------------------------
let figureMode = false;
function imageParagraph(img) {
  const file = path.resolve(BASE, decodeURI(img.href));
  const buf = fs.readFileSync(file);
  const { width, height } = sizeOf(buf);
  const scale = Math.min(MAX_IMG_W / width, MAX_IMG_H / height, 1);
  return new Paragraph({
    alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
    children: [new ImageRun({ type: 'png', data: buf, transformation: { width: Math.round(width * scale), height: Math.round(height * scale) },
      altText: { title: img.text, description: img.text, name: path.basename(file) } })],
  });
}

function table(t) {
  const cols = t.header.length;
  const plain = (cell) => decode(cell.text || '').replace(/\*\*|`/g, '');
  const lens = Array.from({ length: cols }, (_, c) =>
    Math.max(plain(t.header[c]).length, ...t.rows.map((r) => Math.min(plain(r[c]).length, 60)), 4));
  const total = lens.reduce((a, b) => a + b, 0);
  let widths = lens.map((l) => Math.max(Math.round(CONTENT_W * l / total), 700));
  const fix = CONTENT_W - widths.reduce((a, b) => a + b, 0);
  widths[widths.indexOf(Math.max(...widths))] += fix;
  const border = { style: BorderStyle.SINGLE, size: 4, color: 'A6A6A6' };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (c, i, header) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA }, borders,
    shading: header ? { type: ShadingType.CLEAR, color: 'auto', fill: 'D9E2F3' } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    children: [new Paragraph({ spacing: { before: 0, after: 0 }, children: flat(runs(c.tokens, { size: 19, ...(header ? { bold: true } : {}) })) })],
  });
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: t.header.map((c, i) => cell(c, i, true)) }),
      ...t.rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) }))],
  });
}

let listInstance = 0;
function list(t, level = 0) {
  const out = [];
  const instance = ++listInstance;
  for (const item of t.items) {
    const inline = item.tokens.filter((x) => x.type === 'text' || x.type === 'paragraph');
    const nested = item.tokens.filter((x) => x.type === 'list');
    out.push(new Paragraph({
      numbering: { reference: t.ordered ? 'numbers' : 'bullets', level, instance: t.ordered ? instance : undefined },
      spacing: { after: 60 },
      children: flat(inline.map((x) => runs(x.tokens || [{ type: 'text', text: x.text }]))),
    }));
    for (const n of nested) out.push(...list(n, level + 1));
  }
  return out;
}

function blocks(tokens, ctx) {
  const out = [];
  for (const t of tokens) {
    switch (t.type) {
      case 'heading': {
        const text = decode(t.text).replace(/\*\*/g, '');
        let level = t.depth;
        if (ctx.front && level === 2) level = 1;               // Declaration, Abstract ... are top level
        if (level === 1 && /^1\. /.test(text)) ctx.front = false;
        const H = [null, HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4][Math.min(level, 4)];
        out.push(new Paragraph({ heading: H, pageBreakBefore: level === 1 && (ctx.h1Count++ > 0 || ctx.report), keepNext: true, children: [new TextRun(text)] }));
        break;
      }
      case 'paragraph': {
        const imgs = (t.tokens || []).filter((x) => x.type === 'image');
        if (imgs.length) { imgs.forEach((im) => out.push(imageParagraph(im))); figureMode = true; break; }
        const isCaption = figureMode && /^\*Figure \d+/.test(t.raw.trim());
        figureMode = false;
        out.push(new Paragraph(isCaption
          ? { style: 'Caption', alignment: AlignmentType.CENTER, spacing: { after: 240 }, children: flat(runs(t.tokens[0].tokens || t.tokens)) }
          : { spacing: { after: 140 }, children: flat(runs(t.tokens)) }));
        break;
      }
      case 'table': out.push(table(t), new Paragraph({ spacing: { after: 120 }, children: [] })); break;
      case 'list': out.push(...list(t)); break;
      case 'code':
        for (const line of t.text.split('\n')) {
          out.push(new Paragraph({ shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'F2F2F2' }, spacing: { before: 0, after: 0 },
            children: [new TextRun({ text: line || ' ', font: MONO, size: 17 })] }));
        }
        out.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
        break;
      case 'blockquote':
        for (const p of t.tokens.filter((x) => x.type === 'paragraph')) {
          out.push(new Paragraph({ indent: { left: 360 }, spacing: { after: 120 },
            border: { left: { style: BorderStyle.SINGLE, size: 18, color: '8EAADB', space: 8 } },
            shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'F3F6FB' }, children: flat(runs(p.tokens)) }));
        }
        break;
      case 'hr': case 'space': case 'html': break;
      default: if (t.text) out.push(new Paragraph({ children: [textRun(decode(t.text), {})].flat() }));
    }
  }
  return out;
}

// ---- assemble -----------------------------------------------------------------------------------
let md = fs.readFileSync(SRC, 'utf8').replace(/^---\n[\s\S]*?\n---\n/, '');   // drop YAML front matter
const tokens = marked.lexer(md);
const firstH1 = tokens.findIndex((t) => t.type === 'heading' && t.depth === 1);
const declIdx = tokens.findIndex((t) => t.type === 'heading' && t.text === 'Declaration');
const isReport = declIdx >= 0;   // the report has a title page and contents; other documents (KIT.md) do not
const titleTokens = isReport ? tokens.slice(firstH1 + 1, declIdx) : [];
const titleText = decode(tokens[firstH1].text);

const title = !isReport ? [] : [
  new Paragraph({ spacing: { before: 1800, after: 240 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'SmartRestaurant', bold: true, size: 56, color: '1F3864' })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 480 },
    children: [new TextRun({ text: titleText.replace(/^SmartRestaurant: /, ''), size: 30, color: '2F5496' })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: 'CSE5015 Computing Project, HD in Computing & Software Engineering', size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 720 },
    children: [new TextRun({ text: 'Final report (DRAFT, 4 October 2026), Team ForeSight', size: 24, bold: true })] }),
  ...blocks(titleTokens.filter((t) => t.type !== 'paragraph' || !/^\*\*CSE5015/.test(t.raw)), { front: true }),
];

const body = isReport ? blocks(tokens.slice(declIdx), { front: true, report: true, h1Count: 0 })
  : blocks(tokens, { front: false, report: false, h1Count: 0 });

const doc = new Document({
  creator: 'Team ForeSight', title: isReport ? 'SmartRestaurant final report (draft)' : decode(tokens[firstH1].text),
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 22 }, paragraph: { spacing: { line: 276 } } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 32, bold: true, color: '1F3864', font: FONT }, paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 26, bold: true, color: '2F5496', font: FONT }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 23, bold: true, color: '2F5496', font: FONT }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 } },
      { id: 'Caption', name: 'Caption', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 19, italics: true, color: '404040' } },
    ],
  },
  numbering: { config: [
    { reference: 'bullets', levels: [0, 1, 2].map((l) => ({ level: l, format: LevelFormat.BULLET, text: ['•', '◦', '▪'][l],
      alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720 + l * 360, hanging: 360 } } } })) },
    { reference: 'numbers', levels: [0, 1].map((l) => ({ level: l, format: l ? LevelFormat.LOWER_LETTER : LevelFormat.DECIMAL,
      text: `%${l + 1}.`, alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720 + l * 360, hanging: 360 } } } })) },
  ] },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: ['Page ', PageNumber.CURRENT, ' of ', PageNumber.TOTAL_PAGES], size: 18, color: '808080' })] })] }) },
    children: [
      ...(isReport ? [...title,
        new Paragraph({ children: [new PageBreak()] }),
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('Contents')] }),
        new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-2' }),
        new Paragraph({ children: [new TextRun({ text: 'Right-click the table of contents and choose "Update field" if page numbers are missing.', italics: true, size: 18, color: '808080' })] })] : []),
      ...body,
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log('wrote', OUT, buf.length, 'bytes'); });
