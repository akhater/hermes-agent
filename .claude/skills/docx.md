---
name: docx
description: Edit and create Word documents (.docx) using the Anthropic docx toolkit (unpack/pack Python scripts + docx-js + LibreOffice).  Preferred over superdoc for speed.
tags: [docx, word, document, office]
---

# DOCX Manipulation — Fast Native Toolkit

Use this skill for ALL .docx work.  It is faster than the superdoc MCP server because it manipulates XML directly instead of round-tripping through a remote tool.

## Tools Available in This Environment

| Tool | Path | Purpose |
|------|------|---------|
| `pandoc` | system | Convert .docx ↔ .md, extract text |
| `soffice` | system | Convert .doc → .docx or .docx → .pdf |
| `pdftoppm` | system | Convert PDF pages to images |
| `python3` | system | Run docx scripts |
| `node` + `docx` (npm) | system | Create new documents from scratch |

## Scripts (mounted at `/opt/skills/docx/scripts/`)

| Script | Usage |
|--------|-------|
| `python /opt/skills/docx/scripts/office/unpack.py input.docx unpacked/` | Extract .docx to editable XML |
| `python /opt/skills/docx/scripts/office/pack.py unpacked/ output.docx --original input.docx` | Repackage edited XML into .docx |
| `python /opt/skills/docx/scripts/office/validate.py output.docx` | Validate final .docx |
| `python /opt/skills/docx/scripts/accept_changes.py input.docx output.docx` | Accept all tracked changes |
| `python /opt/skills/docx/scripts/comment.py unpacked/ 0 "Comment text"` | Add a comment |
| `python /opt/skills/docx/scripts/office/soffice.py --headless --convert-to pdf file.docx` | Convert to PDF |

## Quick Workflows

### Read / Extract Content
```bash
pandoc --track-changes=all document.docx -o output.md
```

### Edit Existing Document (Surgical)
1. Unpack: `python /opt/skills/docx/scripts/office/unpack.py doc.docx unpacked/`
2. Edit XML files in `unpacked/word/` using the Edit tool directly.
3. Pack: `python /opt/skills/docx/scripts/office/pack.py unpacked/ edited.docx --original doc.docx`
4. Validate: `python /opt/skills/docx/scripts/office/validate.py edited.docx`

### Create New Document (docx-js)
```javascript
const { Document, Packer, Paragraph, TextRun } = require('docx');
const doc = new Document({ sections: [{ children: [new Paragraph("Hello")] }] });
Packer.toBuffer(doc).then(buf => require('fs').writeFileSync("out.docx", buf));
```
Run with: `node script.js`

### Convert .doc → .docx
```bash
python /opt/skills/docx/scripts/office/soffice.py --headless --convert-to docx old.doc
```

## Critical Rules

- **For edits**: ALWAYS unpack → edit XML → pack.  Do not modify .docx as a ZIP manually.
- **For new docs**: Use `docx-js` (Node).  Remember US Letter is `width: 12240, height: 15840` (DXA units).
- **Never use `\n` in docx-js** — use separate `Paragraph` elements.
- **Never use unicode bullets** — use `LevelFormat.BULLET`.
- **Tables need dual widths**: set `columnWidths` array AND cell `width` with `WidthType.DXA`.
- **Smart quotes in XML**: use `&#x2018;` `&#x2019;` `&#x201C;` `&#x201D;`.
- **Tracked changes author**: use `"Claude"` unless user specifies otherwise.
- **Always validate** after pack before delivering to user.

## When to Use Each Approach

| Task | Approach |
|------|----------|
| Extract text/content | `pandoc` |
| Surgical edit existing docx | unpack → Edit tool → pack |
| Bulk replacement of placeholders | unpack → regex/XML edit → pack |
| Create new structured docx | `docx-js` (Node) |
| Convert formats (doc→docx, docx→pdf) | `soffice.py` |
| Add comments / tracked changes | unpack → `comment.py` / manual XML → pack |

## superdoc MCP — Fallback Only

If the native toolkit fails (e.g. super-complex formatting that requires a visual editor), fall back to the `superdoc` MCP tool.  Otherwise, **prefer this skill** for speed.
