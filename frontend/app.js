const API_URL = "/api/convert";

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const dropLabel = document.getElementById("drop-label");
const convertBtn = document.getElementById("convert-btn");
const langSelect = document.getElementById("lang-select");
const statusEl = document.getElementById("status");
const resultSection = document.getElementById("result-section");
const resultMeta = document.getElementById("result-meta");
const pageTabs = document.getElementById("page-tabs");
const output = document.getElementById("output");
const copyBtn = document.getElementById("copy-btn");
const downloadBtn = document.getElementById("download-btn");

let selectedFile = null;
let lastResult = null;

// --- Drop zone ---
dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
});

function setFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("Please select a PDF file.");
    return;
  }
  selectedFile = file;
  dropLabel.textContent = `Selected: ${file.name} (${formatBytes(file.size)})`;
  dropZone.classList.add("has-file");
  dropZone.classList.remove("drag-over");
  convertBtn.disabled = false;
  hideStatus();
  resultSection.classList.add("hidden");
}

// --- Convert ---
convertBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  convertBtn.disabled = true;
  showLoading("Converting… This may take a moment for large or scanned PDFs.");
  resultSection.classList.add("hidden");

  const form = new FormData();
  form.append("file", selectedFile);
  form.append("ocr_lang", langSelect.value);

  try {
    const resp = await fetch(API_URL, { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || "Unknown error");
    }
    const data = await resp.json();
    lastResult = data;
    renderResult(data);
    hideStatus();
  } catch (e) {
    showError(`Error: ${e.message}`);
  } finally {
    convertBtn.disabled = false;
  }
});

const METHOD_LABELS = {
  native:       "Native text",
  "ocr-images": "OCR · embedded images",
  "ocr-raster": "OCR · full-page raster",
};

const ENGINE_LABELS = {
  tesseract: "Tesseract",
  paddleocr: "PaddleOCR",
};

function renderResult(data) {
  const ocrPages  = data.pages.filter((p) => p.method !== "native");
  const paddlePages = data.pages.filter((p) => p.ocr_engine === "paddleocr");
  const cjkPages  = data.pages.filter((p) => p.script === "cjk");

  let meta = `${data.filename} — ${data.page_count} page${data.page_count !== 1 ? "s" : ""}`;
  if (ocrPages.length)   meta += ` · OCR on ${ocrPages.length} page(s)`;
  if (paddlePages.length) meta += ` · PaddleOCR: ${paddlePages.length}`;
  if (cjkPages.length)   meta += ` · CJK detected: ${cjkPages.length}`;
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
  const isOcr  = page && page.method !== "native";
  const isCjk  = page && page.script === "cjk";
  const isPaddle = page && page.ocr_engine === "paddleocr";

  const btn = document.createElement("button");
  const classes = ["page-tab"];
  if (isOcr)    classes.push("ocr");
  if (isCjk)    classes.push("cjk");
  if (isPaddle) classes.push("paddle");
  btn.className = classes.join(" ");

  // Label: page number + small badges
  let display = label;
  if (isCjk)    display += " CJK";
  if (isPaddle) display += " ▲";
  btn.textContent = display;

  if (page) {
    const method  = METHOD_LABELS[page.method] || page.method;
    const engine  = page.ocr_engine ? ` · ${ENGINE_LABELS[page.ocr_engine] || page.ocr_engine}` : "";
    const script  = `script: ${page.script}`;
    btn.title = `${method}${engine} · ${script}`;
  }

  btn.addEventListener("click", () => {
    document.querySelectorAll(".page-tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    output.textContent = text || "(no text)";
  });
  return btn;
}

// --- Copy / Download ---
copyBtn.addEventListener("click", async () => {
  if (!lastResult) return;
  const active = document.querySelector(".page-tab.active");
  await navigator.clipboard.writeText(output.textContent);
  copyBtn.textContent = "Copied!";
  setTimeout(() => (copyBtn.textContent = "Copy text"), 1500);
});

downloadBtn.addEventListener("click", () => {
  if (!lastResult) return;
  const text = output.textContent;
  const baseName = lastResult.filename.replace(/\.pdf$/i, "");
  const blob = new Blob([text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${baseName}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// --- Helpers ---
function showLoading(msg) {
  statusEl.textContent = msg;
  statusEl.className = "status loading";
}
function showError(msg) {
  statusEl.textContent = msg;
  statusEl.className = "status error";
}
function hideStatus() {
  statusEl.className = "status hidden";
}
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
