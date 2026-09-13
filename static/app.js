const $ = (id) => document.getElementById(id);

const dropzone     = $("dropzone");
const fileInput    = $("file-input");
const uploadStage  = $("upload-stage");
const progress     = $("upload-progress");
const progressText = $("progress-text");
const uploadError  = $("upload-error");

const docBar   = $("doc-bar");
const docName  = $("doc-name");
const docStats = $("doc-stats");

const askStage    = $("ask-stage");
const questionBox = $("question");
const askBtn      = $("ask-btn");
const askError    = $("ask-error");
const suggestions = $("suggestions");

const answerStage = $("answer-stage");
const thinking    = $("thinking");
const answerCard  = $("answer-card");
const answerText  = $("answer-text");
const gaugeLabel  = $("gauge-label");
const gaugeValue  = $("gauge-value");
const gaugeFill   = $("gauge-fill");
const gaugeThresh = $("gauge-threshold");
const gaugeNote   = $("gauge-note");
const sourcesBox  = $("sources");
const sourceList  = $("source-list");

const SCALE = 0.8;   // similarity rarely exceeds this, so the bar reads usefully

let docId = null;

const STARTERS = [
  "What is the recommended engine oil grade?",
  "How often should the air filter be replaced?",
  "What is the correct tyre pressure?",
  "What torque should the front axle nut be tightened to?",
];

/* ---------------- helpers ---------------- */

function show(el)  { el.hidden = false; }
function hide(el)  { el.hidden = true; }

function showError(el, message) {
  el.textContent = message;
  show(el);
}

/* ---------------- upload ---------------- */

dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragging");
  })
);

["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragging");
  })
);

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) upload(file);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) upload(fileInput.files[0]);
});

async function upload(file) {
  hide(uploadError);
  hide(dropzone);
  show(progress);
  progressText.textContent = `Reading ${file.name}…`;

  const form = new FormData();
  form.append("file", file);

  try {
    const res = await fetch("/upload", { method: "POST", body: form });
    const data = await res.json();

    if (!res.ok) {
      hide(progress);
      show(dropzone);
      showError(uploadError, data.error || "Upload failed.");
      return;
    }

    docId = data.doc_id;
    docName.textContent = data.filename;

    let stats = `${data.pages} pages · ${data.chunks} searchable sections`;
    if (data.skipped_pages > 0) {
      stats += ` · ${data.skipped_pages} pages had no readable text`;
    }
    docStats.textContent = stats;

    hide(progress);
    hide(uploadStage);
    show(docBar);
    show(askStage);
    renderSuggestions();
    questionBox.focus();

  } catch (err) {
    hide(progress);
    show(dropzone);
    showError(uploadError, "Could not reach the server. Check your connection.");
  }
}

$("change-doc").addEventListener("click", () => {
  docId = null;
  fileInput.value = "";
  hide(docBar);
  hide(askStage);
  hide(answerStage);
  hide(answerCard);
  hide(sourcesBox);
  show(uploadStage);
  show(dropzone);
  hide(uploadError);
});

/* ---------------- suggestions ---------------- */

function renderSuggestions() {
  suggestions.innerHTML = "";
  STARTERS.forEach((text) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.textContent = text;
    btn.addEventListener("click", () => {
      questionBox.value = text;
      ask();
    });
    suggestions.appendChild(btn);
  });
}

/* ---------------- ask ---------------- */

askBtn.addEventListener("click", ask);

questionBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter") ask();
});

async function ask() {
  const question = questionBox.value.trim();
  if (!question || !docId) return;

  hide(askError);
  hide(answerCard);
  hide(sourcesBox);
  show(answerStage);
  show(thinking);
  askBtn.disabled = true;

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId, question }),
    });
    const data = await res.json();

    hide(thinking);
    askBtn.disabled = false;

    if (!res.ok) {
      hide(answerStage);
      showError(askError, data.error || "Something went wrong.");
      return;
    }

    render(data);

  } catch (err) {
    hide(thinking);
    hide(answerStage);
    askBtn.disabled = false;
    showError(askError, "Could not reach the server. Check your connection.");
  }
}

/* ---------------- render ---------------- */

function render(data) {
  answerText.textContent = data.answer;
  answerCard.classList.toggle("refused", data.refused);

  const pct = Math.min(100, (data.top_score / SCALE) * 100);
  const threshPct = (data.threshold / SCALE) * 100;

  gaugeValue.textContent = data.top_score.toFixed(2);
  gaugeThresh.style.left = threshPct + "%";

  // let the bar animate from zero on every answer
  gaugeFill.style.width = "0%";
  requestAnimationFrame(() => { gaugeFill.style.width = pct + "%"; });

  if (!data.refused) {
    gaugeLabel.textContent = "Match strength";
    gaugeNote.textContent =
      `Above the ${data.threshold} cut-off, so the manual was used to answer.`;
  } else if (data.refused_by === "similarity floor") {
    gaugeLabel.textContent = "Match strength — below cut-off";
    gaugeNote.textContent =
      `Nothing in the manual came close enough to the ${data.threshold} cut-off, ` +
      `so no answer was generated.`;
  } else {
    gaugeLabel.textContent = "Match strength — content mismatch";
    gaugeNote.textContent =
      "Relevant pages were found, but they describe something other than what " +
      "you asked about, so the answer was withheld.";
  }

  show(answerCard);

  sourceList.innerHTML = "";
  (data.sources || []).forEach((src) => {
    const li      = document.createElement("li");
    const details = document.createElement("details");
    const summary = document.createElement("summary");

    const page = document.createElement("span");
    page.className = "src-page";
    page.textContent = `Page ${src.page}`;

    const score = document.createElement("span");
    score.className = "src-score";
    score.textContent = src.score.toFixed(2);

    summary.append(page, score);

    const body = document.createElement("p");
    body.className = "src-body";
    body.textContent = src.text;

    details.append(summary, body);
    li.appendChild(details);
    sourceList.appendChild(li);
  });

  if (sourceList.children.length) show(sourcesBox);
}
