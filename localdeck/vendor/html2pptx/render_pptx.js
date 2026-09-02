"use strict";

// This trusted renderer accepts only the JSON geometry produced by exporter.py.
// It never evaluates model-generated JavaScript or invokes a shell.
const fs = require("node:fs");
const path = require("node:path");
const { fileURLToPath } = require("node:url");
const minimist = require("minimist");
const pptxgen = require("pptxgenjs");

function colorToHex(value, fallback = "000000") {
  if (!value || value === "transparent" || value === "rgba(0, 0, 0, 0)") {
    return fallback;
  }
  if (value.startsWith("#")) return value.slice(1).toUpperCase();
  const channels = value.match(/[\d.]+/g);
  if (!channels || channels.length < 3) return fallback;
  return channels.slice(0, 3)
    .map((part) => Math.round(Number(part)).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

function opacityToTransparency(opacity) {
  const safe = Math.max(0, Math.min(1, Number(opacity ?? 1)));
  return Math.round((1 - safe) * 100);
}

function box(element, scaleX, scaleY) {
  return {
    x: element.x * scaleX,
    y: element.y * scaleY,
    w: Math.max(element.w * scaleX, 0.01),
    h: Math.max(element.h * scaleY, 0.01),
  };
}

function addShape(slide, element, scaleX, scaleY, pptx) {
  const style = element.style;
  const hasFill = style.background !== "rgba(0, 0, 0, 0)";
  const hasLine = style.borderWidth > 0;
  slide.addShape(
    style.borderRadius > 0 ? pptx.ShapeType.roundRect : pptx.ShapeType.rect,
    {
      ...box(element, scaleX, scaleY),
      fill: {
        color: colorToHex(style.background, "FFFFFF"),
        transparency: hasFill ? opacityToTransparency(style.opacity) : 100,
      },
      line: {
        color: colorToHex(style.borderColor, "FFFFFF"),
        width: hasLine ? Math.max(style.borderWidth * 0.75, 0.25) : 0,
        transparency: hasLine ? 0 : 100,
      },
      radius: Math.max(style.borderRadius * scaleX, 0),
    },
  );
}

function addText(slide, element, scaleX, scaleY) {
  const style = element.style;
  const text = element.kind === "li" ? `• ${element.text}` : element.text;
  slide.addText(text, {
    ...box(element, scaleX, scaleY),
    margin: 0,
    breakLine: false,
    fontFace: String(style.fontFamily || "Arial").split(",")[0].replace(/["']/g, ""),
    fontSize: Math.max(style.fontSize * 0.75, 6),
    color: colorToHex(style.color, "111827"),
    bold: Number(style.fontWeight) >= 600 || style.fontWeight === "bold",
    italic: style.fontStyle === "italic",
    align: ["left", "center", "right", "justify"].includes(style.textAlign)
      ? style.textAlign
      : "left",
    valign: "mid",
    fit: "shrink",
    transparency: opacityToTransparency(style.opacity),
  });
}

function addImage(slide, element, scaleX, scaleY) {
  let source = element.src;
  if (source.startsWith("file:")) source = fileURLToPath(source);
  if (!fs.existsSync(source)) return;
  slide.addImage({ path: source, ...box(element, scaleX, scaleY) });
}

async function main() {
  const args = minimist(process.argv.slice(2));
  if (!args.input || !args.output) {
    throw new Error("Usage: node render_pptx.js --input spec.json --output deck.pptx");
  }

  const spec = JSON.parse(fs.readFileSync(path.resolve(args.input), "utf8"));
  const pptx = new pptxgen();
  const layoutName = "LOCALDECK";
  pptx.defineLayout({
    name: layoutName,
    width: spec.layout.width,
    height: spec.layout.height,
  });
  pptx.layout = layoutName;
  pptx.author = "LocalDeck";
  pptx.subject = "Docker-free generated presentation";
  pptx.company = "LocalDeck";
  pptx.lang = "zh-CN";

  const scaleX = spec.layout.width / spec.viewport.width;
  const scaleY = spec.layout.height / spec.viewport.height;
  for (const model of spec.slides) {
    const slide = pptx.addSlide();
    slide.background = { color: colorToHex(model.background, "FFFFFF") };
    model.shapes.forEach((element) => addShape(slide, element, scaleX, scaleY, pptx));
    model.images.forEach((element) => addImage(slide, element, scaleX, scaleY));
    model.texts.forEach((element) => addText(slide, element, scaleX, scaleY));
  }

  const output = path.resolve(args.output);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  await pptx.writeFile({ fileName: output });
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message || String(error)}\n`);
  process.exitCode = 1;
});
