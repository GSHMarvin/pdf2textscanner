// ── Tab switching ──────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove("hidden");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// SINGLE FILE
// ══════════════════════════════════════════════════════════════════════════════
const dropZone    = document.getElementById("drop-zone");
const fileInput   = document.getElementById("file-input");
const dropLabel   = document.getElementById("drop-label");
const convertBtn  = document.getElementById("convert-btn");
const langSelect  = document.getElementById("lang-select");
const statusEl    = document.getElementById("status");
const resultSection = document.getElementById("result-section");
const resultMeta  = document.getElementById("result-meta");
const pageTabs    = document.getElementById("page-tabs");
const output      = document.getElementById("output");
const copyBtn     = document.getElementById("copy-btn");
const downloadBtn = document.getElementById("download-btn");

let selectedFile = null;
let lastResult   = null;

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover",  (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setSingleFile(file);
});
fileInput.addEventListener("change", () => { if (fileInput.files[0]) setSingleFile(fileInput.files[0]); });

function setSingleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) { showError(statusEl, "Please select a PDF file."); return; }
  selectedFile = file;
  dropLabel.textContent = `Selected: ${file.name} (${formatBytes(file.size)})`;
  dropZone.classList.add("has-file");
  convertBtn.disabled = false;
  hideStatus(statusEl);
  resultSection.classList.add("hidden");
}

convertBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  convertBtn.disabled = true;
  showLoading(statusEl, "Converting… This may take a moment for large or scanned PDFs.");
  resultSection.classList.add("hidden");

  const form = new FormData();
  form.append("file", selectedFile);
  form.append("ocr_lang", langSelect.value);

  try {
    const resp = await fetch("/api/convert", { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Unknown error");
    }
    lastResult = await resp.json();
    renderResult(lastResult);
    hideStatus(statusEl);
  } catch (e) {
    showError(statusEl, `Error: ${e.message}`);
  } finally {
    convertBtn.disabled = false;
  }
});

const METHOD_LABELS  = { native: "Native text", "ocr-images": "OCR · embedded images", "ocr-raster": "OCR · full-page raster" };
const ENGINE_LABELS  = { tesseract: "Tesseract", paddleocr: "PaddleOCR" };

function renderResult(data) {
  const ocrPages    = data.pages.filter((p) => p.method !== "native");
  const paddlePages = data.pages.filter((p) => p.ocr_engine === "paddleocr");
  const cjkPages    = data.pages.filter((p) => p.script === "cjk");
  let meta = `${data.filename} — ${data.page_count} page${data.page_count !== 1 ? "s" : ""}`;
  if (ocrPages.length)    meta += ` · OCR on ${ocrPages.length} page(s)`;
  if (paddlePages.length) meta += ` · PaddleOCR: ${paddlePages.length}`;
  if (cjkPages.length)    meta += ` · CJK detected: ${cjkPages.length}`;
  resultMeta.textContent = meta;

  pageTabs.innerHTML = "";
  const allTab = makeTab({ label: "All", page: null, text: data.text });
  allTab.classList.add("active");
  pageTabs.appendChild(allTab);
  data.pages.forEach((p) => pageTabs.appendChild(makeTab({ label: `P${p.number}`, page: p, text: p.text })));
  output.textContent = data.text || "(no text extracted)";
  resultSection.classList.remove("hidden");
}

function makeTab({ label, page, text }) {
  const isOcr    = page && page.method !== "native";
  const isCjk    = page && page.script === "cjk";
  const isPaddle = page && page.ocr_engine === "paddleocr";
  const btn = document.createElement("button");
  const classes = ["page-tab"];
  if (isOcr)    classes.push("ocr");
  if (isCjk)    classes.push("cjk");
  if (isPaddle) classes.push("paddle");
  btn.className = classes.join(" ");
  let display = label;
  if (isCjk)    display += " CJK";
  if (isPaddle) display += " ▲";
  btn.textContent = display;
  if (page) {
    const method = METHOD_LABELS[page.method] || page.method;
    const engine = page.ocr_engine ? ` · ${ENGINE_LABELS[page.ocr_engine] || page.ocr_engine}` : "";
    btn.title = `${method}${engine} · script: ${page.script}`;
  }
  btn.addEventListener("click", () => {
    document.querySelectorAll(".page-tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    output.textContent = text || "(no text)";
  });
  return btn;
}

copyBtn.addEventListener("click", async () => {
  if (!lastResult) return;
  await navigator.clipboard.writeText(output.textContent);
  copyBtn.textContent = "Copied!";
  setTimeout(() => (copyBtn.textContent = "Copy text"), 1500);
});
downloadBtn.addEventListener("click", () => {
  if (!lastResult) return;
  const baseName = lastResult.filename.replace(/\.pdf$/i, "");
  triggerDownload(new Blob([output.textContent], { type: "text/plain" }), `${baseName}.txt`);
});

// ══════════════════════════════════════════════════════════════════════════════
// BATCH
// ══════════════════════════════════════════════════════════════════════════════
const batchDropZone   = document.getElementById("batch-drop-zone");
const batchFileInput  = document.getElementById("batch-file-input");
const batchDropLabel  = document.getElementById("batch-drop-label");
const batchBtn        = document.getElementById("batch-btn");
const batchLangSelect = document.getElementById("batch-lang-select");
const csvBtn          = document.getElementById("csv-btn");
const batchStatusEl   = document.getElementById("batch-status");
const batchResultSection = document.getElementById("batch-result-section");
const batchSummary    = document.getElementById("batch-summary");
const batchTbody      = document.getElementById("batch-tbody");

let batchFiles   = [];
let batchResults = [];

batchDropZone.addEventListener("click", () => batchFileInput.click());
batchDropZone.addEventListener("dragover",  (e) => { e.preventDefault(); batchDropZone.classList.add("drag-over"); });
batchDropZone.addEventListener("dragleave", () => batchDropZone.classList.remove("drag-over"));
batchDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  batchDropZone.classList.remove("drag-over");
  setBatchFiles(Array.from(e.dataTransfer.files).filter((f) => f.name.toLowerCase().endsWith(".pdf")));
});
batchFileInput.addEventListener("change", () => {
  setBatchFiles(Array.from(batchFileInput.files));
});

function setBatchFiles(files) {
  if (!files.length) return;
  batchFiles = files;
  batchDropLabel.textContent = `${files.length} PDF${files.length !== 1 ? "s" : ""} selected`;
  batchDropZone.classList.add("has-file");
  batchBtn.disabled = false;
  hideStatus(batchStatusEl);
  batchResultSection.classList.add("hidden");
  csvBtn.classList.add("hidden");
}

batchBtn.addEventListener("click", async () => {
  if (!batchFiles.length) return;

  batchBtn.disabled = true;
  csvBtn.classList.add("hidden");
  batchResults = [];
  batchTbody.innerHTML = "";
  batchResultSection.classList.remove("hidden");
  batchSummary.textContent = "";
  showLoading(batchStatusEl, `Processing ${batchFiles.length} file(s)…`);

  // Process files one at a time so the server isn't overwhelmed
  for (let i = 0; i < batchFiles.length; i++) {
    const file = batchFiles[i];
    addBatchRow(i + 1, file.name, "processing", null);

    const form = new FormData();
    form.append("files", file);
    form.append("ocr_lang", batchLangSelect.value);

    let rowResult;
    try {
      const resp = await fetch("/api/batch", { method: "POST", body: form });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || resp.statusText);
      }
      const data = await resp.json();
      rowResult = data[0];
    } catch (e) {
      rowResult = { filename: file.name, error: e.message };
    }

    batchResults.push(rowResult);
    updateBatchRow(i + 1, rowResult);
  }

  const ok  = batchResults.filter((r) => !r.error).length;
  const err = batchResults.filter((r) =>  r.error).length;
  batchSummary.textContent = `Done — ${ok} succeeded, ${err} failed.`;
  hideStatus(batchStatusEl);
  csvBtn.classList.remove("hidden");
  batchBtn.disabled = false;
});

function addBatchRow(index, filename, status, result) {
  const tr = document.createElement("tr");
  tr.id = `batch-row-${index}`;
  tr.innerHTML = `
    <td>${index}</td>
    <td class="filename-cell" title="${filename}">${filename}</td>
    <td class="status-cell"><span class="badge badge-processing">Processing…</span></td>
    <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
  `;
  batchTbody.appendChild(tr);
}

function updateBatchRow(index, result) {
  const tr = document.getElementById(`batch-row-${index}`);
  if (!tr) return;

  if (result.error) {
    tr.cells[2].innerHTML = `<span class="badge badge-error">Error</span>`;
    tr.cells[3].colSpan = 8;
    tr.cells[3].textContent = result.error;
    tr.classList.add("row-error");
    return;
  }

  tr.cells[2].innerHTML = `<span class="badge badge-ok">OK</span>`;
  tr.classList.add("row-ok");

  const p = result.parsed;
  if (p && p.items && p.items.length > 0) {
    const item = p.items[0];
    tr.cells[3].textContent = p.document_no  || "";
    tr.cells[4].textContent = p.date         || "";
    tr.cells[5].textContent = p.mo_no        || "";
    tr.cells[6].textContent = item.part_no   || "";
    tr.cells[7].textContent = item.name      || "";
    tr.cells[8].textContent = item.qty       != null ? item.qty : "";
    tr.cells[9].textContent = item.batch_no  || "";
    tr.cells[10].textContent = item.warehouse || "";

    // Append extra rows for additional items
    for (let i = 1; i < p.items.length; i++) {
      const it = p.items[i];
      const extra = document.createElement("tr");
      extra.className = "row-ok row-extra";
      extra.innerHTML = `
        <td></td><td></td><td></td>
        <td></td><td></td><td></td>
        <td>${it.part_no   || ""}</td>
        <td>${it.name      || ""}</td>
        <td>${it.qty       != null ? it.qty : ""}</td>
        <td>${it.batch_no  || ""}</td>
        <td>${it.warehouse || ""}</td>
      `;
      tr.insertAdjacentElement("afterend", extra);
    }
  }
}

// CSV export — client-side
csvBtn.addEventListener("click", () => {
  const rows = [["Filename", "Document No", "Date", "Inspection No", "MO No",
                 "Seq", "Category", "Part No", "Product Name", "Warehouse",
                 "Unit", "Qty", "Batch No", "Spec", "Error"]];

  for (const r of batchResults) {
    if (r.error) {
      rows.push([r.filename, "", "", "", "", "", "", "", "", "", "", "", "", "", r.error]);
      continue;
    }
    const p = r.parsed;
    if (!p || !p.items || p.items.length === 0) {
      rows.push([r.filename, p?.document_no || "", p?.date || "", p?.inspection_no || "",
                 p?.mo_no || "", "", "", "", "", "", "", "", "", "", ""]);
      continue;
    }
    for (const item of p.items) {
      rows.push([
        r.filename,
        p.document_no    || "",
        p.date           || "",
        p.inspection_no  || "",
        p.mo_no          || "",
        item.seq         || "",
        item.category    || "",
        item.part_no     || "",
        item.name        || "",
        item.warehouse   || "",
        item.unit        || "",
        item.qty         != null ? item.qty : "",
        item.batch_no    || "",
        item.spec        || "",
        "",
      ]);
    }
  }

  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const bom = "﻿"; // UTF-8 BOM so Excel opens Chinese correctly
  triggerDownload(new Blob([bom + csv], { type: "text/csv;charset=utf-8;" }), "batch_export.csv");
});

function csvCell(val) {
  const s = String(val);
  return /[,"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// ── Shared helpers ─────────────────────────────────────────────────────────
function showLoading(el, msg) { el.textContent = msg; el.className = "status loading"; }
function showError(el, msg)   { el.textContent = msg; el.className = "status error"; }
function hideStatus(el)       { el.className = "status hidden"; }

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function triggerDownload(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
