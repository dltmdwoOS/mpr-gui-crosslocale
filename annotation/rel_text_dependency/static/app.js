const LANGUAGES = ["en", "zh", "fr", "ru", "ja", "th"];
const LANGUAGE_NAMES = { en: "EN", zh: "ZH", fr: "FR", ru: "RU", ja: "JA", th: "TH" };

const state = {
  annotator: "",
  order: 1,
  item: null,
  annotation: null,
  locale: "en",
  compare: false,
  enteredAt: performance.now(),
  summaries: [],
  saving: false,
};

const $ = (id) => document.getElementById(id);

function escapeText(value) {
  return value == null || value === "" ? "번역 없음 — 영어 원문을 사용하세요." : String(value);
}

function renderOptions(element, options, order = ["A", "B", "C", "D"], correctAnswer = null) {
  element.innerHTML = "";
  order.forEach((label) => {
    const li = document.createElement("li");
    if (label === correctAnswer) li.classList.add("correct-option");
    const badge = document.createElement("span");
    badge.className = "option-label";
    badge.textContent = label;
    li.appendChild(badge);
    li.appendChild(document.createTextNode(escapeText(options?.[label])));
    element.appendChild(li);
  });
}

function setProgress(progress) {
  const percent = progress.total ? (100 * progress.labeled / progress.total) : 0;
  $("progressBar").style.width = `${percent}%`;
  $("progressText").textContent = `완료 ${progress.labeled} · 남음 ${progress.remaining} · 검토 ${progress.review}`;
}

async function refreshSummaries() {
  const response = await fetch(`/api/items?annotator=${encodeURIComponent(state.annotator)}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  state.summaries = payload.items;
  setProgress(payload.progress);
}

function updateLocale() {
  if (!state.item) return;
  const locale = state.item.locales[state.locale];
  $("mainImage").src = locale.image_url;
  $("mainCaption").textContent = `${LANGUAGE_NAMES[state.locale]} GUI`;
  $("localeQuestion").textContent = locale.question_stem;
  renderOptions($("localeOptions"), locale.options, locale.option_order, locale.correct_answer);
  document.querySelectorAll(".locale-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.locale === state.locale);
  });

  const compareLocale = state.locale === "en" ? "zh" : "en";
  $("compareImage").src = state.item.locales[compareLocale].image_url;
  $("compareCaption").textContent = `${LANGUAGE_NAMES[compareLocale]} GUI`;
  $("compareCard").classList.toggle("hidden", !state.compare);
  $("compareButton").textContent = state.compare ? "비교 닫기" : "EN과 비교";
}

function renderDecision() {
  const label = state.annotation?.label || null;
  $("dependentButton").classList.toggle("selected", label === "dependent");
  $("independentButton").classList.toggle("selected", label === "independent");
  $("reviewFlag").checked = Boolean(state.annotation?.review_flag);
  $("note").value = state.annotation?.note || "";
}

function renderItem(payload) {
  state.item = payload.item;
  state.annotation = payload.annotation || { label: null, review_flag: false, note: "" };
  state.locale = state.annotation.current_locale || "en";
  state.enteredAt = performance.now();
  $("itemCounter").textContent = `${state.order} / ${payload.total_items}`;
  $("parallelId").textContent = state.item.parallel_id;
  $("stratumBadge").textContent = `source stratum ${state.item.stratum}`;

  const english = state.item.locales.en;
  const korean = state.item.ko_helper || {};
  $("koQuestion").textContent = escapeText(korean.question_stem);
  renderOptions($("koOptions"), korean, ["A", "B", "C", "D"], english.correct_answer);
  $("enQuestion").textContent = english.question_stem;
  renderOptions($("enOptions"), english.options, english.option_order, english.correct_answer);
  updateLocale();
  renderDecision();
  $("saveStatus").textContent = state.annotation?.updated_at ? `저장됨 · ${state.annotation.updated_at}` : "아직 미분류";
}

async function loadItem(order) {
  state.order = Math.max(1, Math.min(window.ANNOTATION_CONFIG.totalItems, order));
  const response = await fetch(`/api/item/${state.order}?annotator=${encodeURIComponent(state.annotator)}`);
  if (!response.ok) throw new Error(await response.text());
  renderItem(await response.json());
}

async function save({ label = undefined, autoNext = false } = {}) {
  if (!state.item || state.saving) return;
  state.saving = true;
  $("saveStatus").textContent = "저장 중…";
  if (label !== undefined) state.annotation.label = label;
  state.annotation.review_flag = $("reviewFlag").checked;
  state.annotation.note = $("note").value;
  const elapsed = (performance.now() - state.enteredAt) / 1000;
  const response = await fetch("/api/annotate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      annotator_id: state.annotator,
      parallel_id: state.item.parallel_id,
      label: state.annotation.label || null,
      review_flag: state.annotation.review_flag,
      note: state.annotation.note,
      current_locale: state.locale,
      annotation_seconds: elapsed,
    }),
  });
  state.saving = false;
  if (!response.ok) {
    $("saveStatus").textContent = "저장 실패";
    throw new Error(await response.text());
  }
  const payload = await response.json();
  state.annotation = payload.saved;
  setProgress(payload.progress);
  renderDecision();
  $("saveStatus").textContent = "저장 완료";
  state.enteredAt = performance.now();
  if (autoNext && state.order < window.ANNOTATION_CONFIG.totalItems) {
    await loadItem(state.order + 1);
  }
}

function cycleLocale(delta) {
  const index = LANGUAGES.indexOf(state.locale);
  state.locale = LANGUAGES[(index + delta + LANGUAGES.length) % LANGUAGES.length];
  updateLocale();
}

function buildLocaleTabs() {
  LANGUAGES.forEach((locale) => {
    const button = document.createElement("button");
    button.className = "locale-tab";
    button.dataset.locale = locale;
    button.textContent = LANGUAGE_NAMES[locale];
    button.addEventListener("click", () => { state.locale = locale; updateLocale(); });
    $("localeTabs").appendChild(button);
  });
}

async function start() {
  const annotator = $("annotatorInput").value.trim();
  if (!/^[A-Za-z0-9가-힣_.-]{1,80}$/.test(annotator)) {
    alert("Annotator ID 형식을 확인하세요.");
    return;
  }
  state.annotator = annotator;
  localStorage.setItem("relAnnotatorId", annotator);
  $("annotatorBadge").textContent = annotator;
  $("loginOverlay").classList.add("hidden");
  await refreshSummaries();
  const firstUnlabeled = state.summaries.find((item) => !item.label);
  await loadItem(firstUnlabeled?.display_order || 1);
}

function openZoom() {
  $("zoomImage").src = $("mainImage").src;
  $("zoomOverlay").classList.remove("hidden");
}

function closeZoom() { $("zoomOverlay").classList.add("hidden"); }

buildLocaleTabs();
$("startButton").addEventListener("click", () => start().catch(console.error));
$("annotatorInput").addEventListener("keydown", (event) => { if (event.key === "Enter") start().catch(console.error); });
$("dependentButton").addEventListener("click", () => save({ label: "dependent", autoNext: true }).catch(console.error));
$("independentButton").addEventListener("click", () => save({ label: "independent", autoNext: true }).catch(console.error));
$("saveButton").addEventListener("click", () => save().catch(console.error));
$("previousButton").addEventListener("click", () => loadItem(state.order - 1).catch(console.error));
$("nextButton").addEventListener("click", () => loadItem(state.order + 1).catch(console.error));
$("compareButton").addEventListener("click", () => { state.compare = !state.compare; updateLocale(); });
$("zoomButton").addEventListener("click", openZoom);
$("mainImage").addEventListener("dblclick", openZoom);
$("closeZoom").addEventListener("click", closeZoom);
$("zoomOverlay").addEventListener("click", (event) => { if (event.target === $("zoomOverlay")) closeZoom(); });
$("exportButton").addEventListener("click", () => { window.location = `/api/export?annotator=${encodeURIComponent(state.annotator)}`; });
$("reviewFlag").addEventListener("change", () => save().catch(console.error));
$("note").addEventListener("blur", () => save().catch(console.error));

document.addEventListener("keydown", (event) => {
  if (!state.annotator || ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (event.key === "1") save({ label: "dependent", autoNext: true }).catch(console.error);
  else if (event.key === "2") save({ label: "independent", autoNext: true }).catch(console.error);
  else if (event.key.toLowerCase() === "f") { $("reviewFlag").checked = !$("reviewFlag").checked; save().catch(console.error); }
  else if (event.key.toLowerCase() === "s") save().catch(console.error);
  else if (event.key.toLowerCase() === "k" || event.key === "ArrowRight") loadItem(state.order + 1).catch(console.error);
  else if (event.key.toLowerCase() === "j" || event.key === "ArrowLeft") loadItem(state.order - 1).catch(console.error);
  else if (event.key === "]") cycleLocale(1);
  else if (event.key === "[") cycleLocale(-1);
  else if (event.key.toLowerCase() === "z") openZoom();
  else if (event.key === "Escape") closeZoom();
});

const requestedAnnotator = new URLSearchParams(window.location.search).get("annotator");
const remembered = requestedAnnotator || localStorage.getItem("relAnnotatorId");
if (remembered) $("annotatorInput").value = remembered;
if (requestedAnnotator) start().catch(console.error);
