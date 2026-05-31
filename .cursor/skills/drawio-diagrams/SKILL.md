---
name: drawio-diagrams
description: Creates and edits draw.io diagram XML (.drawio) for local viewers. Use when the user asks for draw.io, diagrams.net, mxfile, architecture diagrams, flowcharts, or modifying .drawio files.
---

# draw.io Diagrams

## Purpose

Create and edit editable `.drawio` XML files for the user's local draw.io / diagrams.net-compatible viewer.

Default to direct, uncompressed XML that can be reviewed in git and opened locally. Do not assume an in-IDE preview. Do not export PNG/SVG or build a viewer unless the user explicitly asks.

## Reference Use

This skill includes the rules needed for normal diagram generation and editing.

Only read [drawio-xml-reference.md](drawio-xml-reference.md) when you need specificity that is not covered here, such as:

- uncommon `shape=` values or stencil libraries
- detailed style key behavior
- specialized edge routing, arrowheads, or perimeter values
- HTML label patterns beyond simple bold text and line breaks
- examples for UML, grouped diagrams, metadata objects, or advanced geometry

Do not read the reference file by default for ordinary flowcharts, architecture diagrams, simple element graphs, or small edits.

## Core File Rules

- Use `.drawio` files containing UTF-8 XML.
- Use uncompressed `<mxGraphModel>` inside `<diagram>`. Do not generate compressed/base64 diagram content.
- Preserve existing `mxfile`, `diagram`, and `mxGraphModel` metadata when editing unless replacement is requested.
- Every diagram needs the two structural cells first:

```xml
<mxCell id="0"/>
<mxCell id="1" parent="0"/>
```

- User-visible vertices and edges usually use `parent="1"`, unless they belong to a layer, group, or swimlane.
- Every `mxCell` id must be unique within the diagram.
- Vertices use `vertex="1"` and edges use `edge="1"`; do not set both.
- Vertices need `<mxGeometry x="..." y="..." width="..." height="..." as="geometry"/>`.
- Connected edges should set `source` and `target` to existing vertex ids and use `<mxGeometry relative="1" as="geometry"/>`.
- Style strings are semicolon-separated, case-sensitive `key=value;` pairs. Bare tokens such as `ellipse;` or `text;` are allowed style/class shortcuts.

## Minimal File Template

Use this for new diagrams unless an existing local convention says otherwise.

```xml
<mxfile host="app.diagrams.net" agent="Pyllments" version="1.0">
  <diagram id="page-1" name="Page-1">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

## Common Cell Patterns

### Vertex

```xml
<mxCell id="service-1" value="Service" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#DAE8FC;strokeColor=#6C8EBF;" vertex="1" parent="1">
  <mxGeometry x="120" y="80" width="160" height="60" as="geometry"/>
</mxCell>
```

### Connected Edge

```xml
<mxCell id="edge-1" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=classic;" edge="1" parent="1" source="service-1" target="service-2">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

### Edge Label

Use the edge cell's `value` for simple labels.

```xml
<mxCell id="edge-2" value="payload" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=classic;" edge="1" parent="1" source="a" target="b">
  <mxGeometry x="0" y="0" relative="1" as="geometry">
    <mxPoint as="offset"/>
  </mxGeometry>
</mxCell>
```

## Default Styles

Use these only when the user has not provided a stronger style preference.

| Type | Style |
|------|-------|
| Generic box | `rounded=1;whiteSpace=wrap;html=1;fillColor=#DAE8FC;strokeColor=#6C8EBF;` |
| Process / element | `rounded=1;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;` |
| Decision | `rhombus;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;` |
| Storage | `shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fillColor=#DAE8FC;strokeColor=#6C8EBF;` |
| External / warning | `rounded=1;whiteSpace=wrap;html=1;fillColor=#F8CECC;strokeColor=#B85450;` |
| Group / container | `swimlane;startSize=28;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#666666;fontStyle=1;` |
| Text note | `text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=top;whiteSpace=wrap;` |
| Default edge | `edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=classic;` |
| Dashed edge | `edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=classic;dashed=1;` |
| Bidirectional edge | `edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=classic;startArrow=classic;` |

If the user adds a project-specific style section later, treat that as the source of truth and override these defaults.

## Layout Guidance

- Favor readable diagrams over dense packing.
- Use grid-aligned coordinates and round dimensions.
- Common default vertex size: `160x60`; storage: `120x80`; group containers: size to fit children plus margin.
- Left-to-right flows: increase `x` by width + 80 to 120; keep related nodes aligned by `y`.
- Top-to-bottom flows: increase `y` by height + 70 to 100.
- In grouped cells, child coordinates are relative to the group, not the page.
- Add waypoints only when needed; simple connected edges usually route well without them.

## HTML Label Rules

- If `html=1`, XML-escape label HTML inside `value`.
- Common escapes: `<` → `&lt;`, `>` → `&gt;`, `&` → `&amp;`, `"` → `&quot;`.
- Prefer simple labels unless the user asks for rich formatting.
- For a title plus detail, use:

```xml
value="&lt;b&gt;Title&lt;/b&gt;&lt;br&gt;Detail"
```

## Editing Workflow

1. Read the target `.drawio` file before editing.
2. Identify whether the diagram content is uncompressed XML. If compressed/non-XML, ask whether to re-save uncompressed or proceed by replacing with uncompressed XML.
3. Preserve unrelated pages, cells, ids, styles, metadata, and geometry.
4. When adding cells, scan existing ids and choose new unique ids. Do not renumber old ids.
5. When deleting a vertex, also remove edges whose `source` or `target` references it.
6. Re-check all new `parent`, `source`, and `target` references after editing.

## Creation Workflow

1. Clarify diagram type and audience if not obvious.
2. Choose a simple layout: left-to-right, top-to-bottom, or grouped/swimlane.
3. Create vertices first, then edges.
4. Use stable ids that are easy to read (`element-chat`, `port-output`, `edge-chat-to-llm`) unless matching an existing numeric-id file.
5. Save the `.drawio` file at the user-specified path, or suggest a conventional path if none is given.
6. Tell the user the file is ready to open in their local viewer.

## Quality Checklist

- [ ] XML is well-formed.
- [ ] `<mxfile>` contains at least one `<diagram>`.
- [ ] `<root>` contains `id="0"` and `id="1" parent="0"`.
- [ ] All ids are unique.
- [ ] Each content cell has exactly one of `vertex="1"` or `edge="1"`.
- [ ] All `parent`, `source`, and `target` references resolve.
- [ ] Vertex geometries have positive `width` and `height`.
- [ ] Edge geometries use `relative="1"`.
- [ ] HTML labels are XML-escaped.
- [ ] Styles end with semicolons and use valid draw.io-style key/value syntax.
- [ ] Unrelated cells were not changed during edits.

## Future Validator

When a validator is added, run it after every create/edit operation and fix reported issues before finishing.
