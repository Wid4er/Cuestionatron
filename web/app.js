"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const number = (value, digits = 2) => new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits }).format(value);
const plural = (count, singular, many) => `${count} ${count === 1 ? singular : many}`;
const GOOSE_PROBABILITY = 0.001; // 0,1 %: una posibilidad entre mil por pregunta e intento.
const state = { catalog: [], selected: new Set(), session: null, answers: {}, index: 0, result: null, filter: "all", busy: false, lastConfig: null, gooseQuestions: new Set() };
let dialogAction = null;
let balloonTimer = null;

function stopCelebration() {
  clearTimeout(balloonTimer);
  balloonTimer = null;
  $("#balloon-layer").replaceChildren();
  $("#celebration-banner").hidden = true;
  const audio = $("#celebration-audio");
  audio.pause();
  audio.currentTime = 0;
}

async function playCelebrationMusic() {
  if (!state.result || state.result.score < 9 || $("#results-view").hidden) return;
  const audio = $("#celebration-audio");
  try {
    await audio.play();
    if ($("#results-view").hidden || !state.result || state.result.score < 9) audio.pause();
  } catch {
    // Si el navegador requiere otro clic, el botón permite iniciar la música.
    $("#celebration-music-button").textContent = "Reproducir música";
  }
}

function startCelebration() {
  stopCelebration();
  if (!state.result || state.result.score < 9) return;
  $("#celebration-banner").hidden = false;
  const colors = ["#a898f0", "#e9a2b9", "#91ceb7", "#f0cd82", "#94bfe8", "#c1abe5"];
  for (let index = 0; index < 18; index++) {
    const balloon = element("span", "balloon");
    balloon.style.setProperty("--balloon-left", `${3 + (index * 29) % 92}%`);
    balloon.style.setProperty("--balloon-color", colors[index % colors.length]);
    balloon.style.setProperty("--balloon-delay", `${(index % 6) * 0.65}s`);
    balloon.style.setProperty("--balloon-duration", `${12 + (index % 4) * 1.5}s`);
    balloon.style.setProperty("--balloon-sway", `${index % 2 ? 45 : -45}px`);
    $("#balloon-layer").append(balloon);
  }
  balloonTimer = setTimeout(() => $("#balloon-layer").replaceChildren(), 22000);
  playCelebrationMusic();
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function notify(message) {
  const notice = $("#notice");
  notice.textContent = message || "";
  notice.hidden = !message;
  if (message) notice.scrollIntoView({ block: "center", behavior: "smooth" });
}

async function api(path, data) {
  let response;
  try {
    response = await fetch(path, data === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
  } catch {
    throw new Error("No se puede conectar con Cuestionatron. Comprueba que el programa sigue abierto en la terminal.");
  }
  let body;
  try { body = await response.json(); }
  catch { throw new Error("El servidor ha devuelto una respuesta inesperada. Vuelve a intentarlo."); }
  if (!response.ok) throw new Error(body.error || "No se pudo completar la operación.");
  return body;
}

function showView(view) {
  if (view !== "results") stopCelebration();
  ["setup", "quiz", "results"].forEach((name, index) => {
    $(`#${name}-view`).hidden = view !== name;
    const step = $(`[data-step="${name}"]`);
    step.classList.toggle("active", view === name);
    step.classList.toggle("done", index < ["setup", "quiz", "results"].indexOf(view));
    if (view === name) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  $("#breadcrumb").textContent = { setup: "Biblioteca / Nuevo test", quiz: "Tu test / En práctica", results: "Tu test / Resultados" }[view];
  notify("");
  const title = $({ setup: "#setup-title", quiz: "#quiz-title", results: "#results-title" }[view]);
  title.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "instant" });
}

function saveSettings() {
  try {
    localStorage.setItem("cuestionatron.settings.v1", JSON.stringify({
      quizzes: [...state.selected], answer_count: $("#answer-count").valueAsNumber,
      penalty: $("#penalty").valueAsNumber, shuffle: $("#shuffle").checked,
      question_limit: $("#all-questions").checked ? null : $("#question-limit").valueAsNumber,
    }));
  } catch { /* La práctica también funciona con el almacenamiento bloqueado. */ }
}

function restoreSettings() {
  try {
    const settings = JSON.parse(localStorage.getItem("cuestionatron.settings.v1") || "null");
    if (!settings || typeof settings !== "object") return;
    if (Array.isArray(settings.quizzes)) state.selected = new Set(settings.quizzes.filter((name) => typeof name === "string"));
    if (Number.isInteger(settings.answer_count) && settings.answer_count >= 2 && settings.answer_count <= 21) $("#answer-count").value = settings.answer_count;
    if (Number.isFinite(settings.penalty) && settings.penalty >= 0 && settings.penalty <= 10) $("#penalty").value = settings.penalty;
    if (typeof settings.shuffle === "boolean") $("#shuffle").checked = settings.shuffle;
    if (settings.question_limit === null) $("#all-questions").checked = true;
    else if (Number.isInteger(settings.question_limit) && settings.question_limit > 0) $("#question-limit").value = settings.question_limit;
  } catch { /* Un ajuste guardado no válido se sustituye por el predeterminado. */ }
}

function updatePresets() {
  const value = $("#penalty").valueAsNumber;
  $$("[data-penalty]").forEach((button) => {
    const active = Number(button.dataset.penalty) === value;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function visibleQuizzes() {
  const search = $("#search").value.trim().toLocaleLowerCase("es");
  return state.catalog.filter((quiz) => quiz.name.toLocaleLowerCase("es").includes(search));
}

function updateSelection() {
  const quizzes = state.catalog.filter((quiz) => state.selected.has(quiz.id) && !quiz.error);
  const total = quizzes.reduce((count, quiz) => count + quiz.count, 0);
  const allQuestions = $("#all-questions").checked;
  const limit = $("#question-limit").valueAsNumber;
  const validLimit = allQuestions || (Number.isSafeInteger(limit) && limit > 0);
  $("#question-limit").disabled = allQuestions;
  const count = allQuestions ? total : validLimit ? Math.min(total, limit) : 0;
  $("#selection-total").textContent = plural(count, "pregunta", "preguntas");
  $("#selection-sources").textContent = quizzes.length ? `${plural(total, "disponible", "disponibles")} en ${plural(quizzes.length, "cuestionario", "cuestionarios")} · Nota sobre 10` : "Selecciona un cuestionario para empezar";
  $("#start-button").disabled = total === 0 || !validLimit || state.busy;
  const visible = visibleQuizzes().filter((quiz) => !quiz.error);
  const allSelected = visible.length > 0 && visible.every((quiz) => state.selected.has(quiz.id));
  $("#select-all").textContent = allSelected ? "Quitar selección" : "Seleccionar todos";
  $("#select-all").disabled = visible.length === 0;
  saveSettings();
}

function renderCatalog() {
  const list = $("#catalog");
  list.replaceChildren();
  $("#library-count").textContent = state.catalog.filter((quiz) => !quiz.error).length;
  const quizzes = visibleQuizzes();
  if (!quizzes.length) {
    list.append(element("p", "empty-state", state.catalog.length ? "No hay cuestionarios con ese nombre." : "Tu biblioteca está lista para llenarse. Añade archivos .md a la carpeta Cuestionarios y pulsa actualizar."));
  }
  for (const quiz of quizzes) {
    const card = element(quiz.error ? "div" : "label", `quiz-card${state.selected.has(quiz.id) ? " selected" : ""}${quiz.error ? " invalid" : ""}`);
    const icon = element("span", "quiz-card-icon", quiz.error ? "!" : "≡");
    icon.setAttribute("aria-hidden", "true");
    const details = element("div", "quiz-card-details");
    const title = element("h3", "", quiz.name);
    details.append(title);
    if (quiz.error) details.append(element("p", "card-error", quiz.error));
    else {
      const meta = element("div", "card-meta");
      meta.append(element("span", "", plural(quiz.count, "pregunta", "preguntas")));
      if (quiz.multiple) meta.append(element("span", "", `· ${quiz.multiple} de selección múltiple`));
      details.append(meta);
    }
    card.append(icon, details);
    if (!quiz.error) {
      const input = element("input");
      input.type = "checkbox";
      input.checked = state.selected.has(quiz.id);
      input.setAttribute("aria-label", `Seleccionar ${quiz.name}`);
      input.addEventListener("change", () => {
        if (input.checked) state.selected.add(quiz.id);
        else state.selected.delete(quiz.id);
        card.classList.toggle("selected", input.checked);
        updateSelection();
      });
      card.append(input);
    }
    list.append(card);
  }
  updateSelection();
}

async function loadCatalog() {
  $("#refresh-button").disabled = true;
  $("#refresh-button").setAttribute("aria-busy", "true");
  try {
    const data = await api("/api/catalog");
    state.catalog = data.quizzes;
    const valid = new Set(state.catalog.filter((quiz) => !quiz.error).map((quiz) => quiz.id));
    state.selected = new Set([...state.selected].filter((id) => valid.has(id)));
    renderCatalog();
    notify("");
  } catch (error) {
    notify(error.message);
    $("#catalog").replaceChildren(element("p", "empty-state", "No se pudo actualizar la biblioteca. Pulsa ↻ para volver a intentarlo."));
    // Un catálogo sin actualizar no debe permitir iniciar un test antiguo.
    state.catalog = [];
    updateSelection();
  } finally {
    $("#refresh-button").disabled = false;
    $("#refresh-button").removeAttribute("aria-busy");
  }
}

async function startTest(config) {
  if (state.busy) return;
  stopCelebration();
  state.busy = true;
  $("#start-button").disabled = true;
  $("#retry-button").disabled = true;
  $("#start-button").textContent = "Preparando tu test…";
  try {
    const session = await api("/api/start", config);
    state.session = session;
    // Un único sorteo por pregunta: volver atrás o cambiar una respuesta no lo repite.
    state.gooseQuestions = new Set(session.questions.filter(() => Math.random() < GOOSE_PROBABILITY).map((question) => question.id));
    state.lastConfig = structuredClone(config);
    state.answers = {};
    state.index = 0;
    state.result = null;
    $("#penalty-reminder").textContent = `Cada fallo resta ${number(session.penalty, 20)} ${session.penalty === 1 ? "acierto" : "aciertos"}. En blanco: 0.`;
    renderQuestion();
    showView("quiz");
  } catch (error) { notify(error.message); }
  finally {
    state.busy = false;
    $("#retry-button").disabled = false;
    const arrow = element("span", "", "↗");
    arrow.setAttribute("aria-hidden", "true");
    $("#start-button").replaceChildren(document.createTextNode("Empezar test "), arrow);
    updateSelection();
  }
}

function answeredCount() { return Object.values(state.answers).filter((choices) => choices.length > 0).length; }

function updateQuestionMap() {
  const map = $("#question-map");
  map.replaceChildren();
  state.session.questions.forEach((question, index) => {
    const answered = Boolean(state.answers[question.id]?.length);
    const button = element("button", `${answered ? "answered " : ""}${index === state.index ? "current" : ""}`, String(index + 1));
    button.type = "button";
    button.setAttribute("aria-label", `Pregunta ${index + 1}, ${answered ? "respondida" : "pendiente"}`);
    if (index === state.index) button.setAttribute("aria-current", "true");
    button.addEventListener("click", () => navigateQuestion(index));
    map.append(button);
  });
  $("#answered-count").textContent = `${answeredCount()} de ${state.session.questions.length} respondidas`;
}

function renderQuestion() {
  const question = state.session.questions[state.index];
  $(".question-panel").classList.toggle("with-goose", state.gooseQuestions.has(question.id));
  const total = state.session.questions.length;
  $("#question-position").textContent = `Pregunta ${state.index + 1} de ${total}`;
  $("#question-source").textContent = question.source;
  $("#progress-bar").style.width = `${((state.index + 1) / total) * 100}%`;
  $("#quiz-title").textContent = question.text;
  $("#question-instruction").textContent = question.multiple ? "Selección múltiple · Marca todas las respuestas correctas." : "Una respuesta correcta · Elige una opción.";
  const list = $("#answers");
  list.replaceChildren();
  for (const [index, option] of question.options.entries()) {
    const label = element("label", "answer");
    const letter = element("span", "answer-letter", index < 26 ? String.fromCharCode(65 + index) : String(index + 1));
    letter.setAttribute("aria-hidden", "true");
    const input = element("input");
    input.type = question.multiple ? "checkbox" : "radio";
    input.name = question.id;
    input.value = option.id;
    input.checked = (state.answers[question.id] || []).includes(option.id);
    input.addEventListener("change", () => {
      state.answers[question.id] = [...list.querySelectorAll("input:checked")].map((node) => node.value);
      $("#clear-answer").disabled = state.answers[question.id].length === 0;
      updateQuestionMap();
    });
    label.append(letter, element("span", "answer-text", option.text), input);
    list.append(label);
  }
  $("#clear-answer").disabled = !(state.answers[question.id]?.length);
  $("#previous-button").disabled = state.index === 0;
  $("#next-button").textContent = state.index === total - 1 ? "Finalizar y corregir" : "Siguiente →";
  updateQuestionMap();
}

function navigateQuestion(index) {
  if (state.busy || index < 0 || index >= state.session.questions.length) return;
  state.index = index;
  renderQuestion();
  $("#quiz-title").focus({ preventScroll: true });
  $("#quiz-view").scrollIntoView({ block: "start", behavior: "smooth" });
}

function confirmAction(title, message, label, action) {
  if (state.busy) return;
  dialogAction = action;
  $("#dialog-title").textContent = title;
  $("#dialog-description").textContent = message;
  $("#dialog-confirm").textContent = label;
  $("#confirm-dialog").returnValue = "cancel";
  $("#confirm-dialog").showModal();
}

function requestFinish() {
  const blank = state.session.questions.length - answeredCount();
  const message = blank ? `Tienes ${plural(blank, "pregunta en blanco", "preguntas en blanco")}. No restarán puntos. Al corregir podrás ver la nota y repasar todas las respuestas.` : "Has respondido todas las preguntas. Al corregir podrás ver tu nota y repasar las respuestas.";
  confirmAction("¿Corregimos tu test?", message, "Ver mi resultado", finishTest);
}

async function finishTest() {
  if (state.busy) return;
  state.busy = true;
  $("#finish-button").disabled = true;
  $("#next-button").disabled = true;
  try {
    state.result = await api("/api/grade", { session_id: state.session.session_id, answers: state.answers });
    state.filter = "all";
    renderResults();
    showView("results");
    startCelebration();
  } catch (error) { notify(error.message); }
  finally {
    state.busy = false;
    $("#finish-button").disabled = false;
    $("#next-button").disabled = false;
  }
}

function renderResults() {
  const result = state.result;
  $("#result-subtitle").textContent = `${plural(result.total, "pregunta", "preguntas")} · ${plural(state.lastConfig.quizzes.length, "cuestionario", "cuestionarios")} · Un paso más en tu aprendizaje.`;
  $("#score-value").textContent = number(result.score);
  $("#score-ring").style.strokeDashoffset = String(320.442 * (1 - result.score / 10));
  $("#score-message").textContent = result.score >= 9 ? "Lo tienes dominado." : result.score >= 7 ? "Vas por muy buen camino." : result.score >= 5 ? "Una buena base para seguir." : "Cada repaso suma.";
  $("#score-formula").textContent = `(${result.correct} − ${result.incorrect} × ${number(result.penalty, 20)}) ÷ ${result.total} × 10${result.net < 0 ? ". La nota mínima es 0." : ""}`;
  $("#correct-total").textContent = result.correct;
  $("#incorrect-total").textContent = result.incorrect;
  $("#blank-total").textContent = result.blank;
  renderReview();
}

function renderReview() {
  const list = $("#review-list");
  list.replaceChildren();
  $$("[data-filter]").forEach((button) => {
    const active = button.dataset.filter === state.filter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  state.result.review.forEach((question, index) => {
    if (state.filter !== "all" && question.status !== state.filter) return;
    const card = element("article", "review-card");
    const header = element("div", "review-card-header");
    header.append(element("span", "", `${String(index + 1).padStart(2, "0")} / ${question.source}${question.multiple ? " · Selección múltiple" : ""}`));
    header.append(element("span", `status-label ${question.status}`, { correct: "Acertada", incorrect: "Incorrecta", blank: "En blanco" }[question.status]));
    card.append(header, element("h3", "", question.text));
    const options = element("div", "review-options");
    for (const option of question.options) {
      const selected = question.selected.includes(option.id);
      const status = option.correct ? "correct" : selected ? "wrong" : "";
      const row = element("div", `review-option ${status}${selected ? " selected" : ""}`);
      row.append(element("span", "", option.correct ? "✓" : selected ? "×" : "·"), element("span", "", option.text));
      const note = selected ? "Tu respuesta" : option.correct ? "Correcta" : "";
      if (note) row.append(element("span", "option-note", note));
      options.append(row);
    }
    card.append(options);
    if (question.multiple && question.status !== "correct") card.append(element("p", "review-note", "Para acertar esta pregunta tenías que marcar todas las respuestas correctas y ninguna incorrecta."));
    list.append(card);
  });
  if (!list.children.length) list.append(element("p", "empty-state", state.filter === "incorrect" ? "No tienes fallos que repasar. ¡Buen trabajo!" : "No dejaste ninguna pregunta en blanco."));
}

$("#settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!$("#settings-form").reportValidity()) return;
  saveSettings();
  startTest({ quizzes: [...state.selected], answer_count: $("#answer-count").valueAsNumber, penalty: $("#penalty").valueAsNumber, shuffle: $("#shuffle").checked, question_limit: $("#all-questions").checked ? null : $("#question-limit").valueAsNumber });
});
$("#refresh-button").addEventListener("click", loadCatalog);
$("#search").addEventListener("input", renderCatalog);
$("#select-all").addEventListener("click", () => {
  const visible = visibleQuizzes().filter((quiz) => !quiz.error);
  const remove = visible.every((quiz) => state.selected.has(quiz.id));
  visible.forEach((quiz) => remove ? state.selected.delete(quiz.id) : state.selected.add(quiz.id));
  renderCatalog();
});
$("#less-options").addEventListener("click", () => {
  $("#answer-count").value = Math.max(2, (Number($("#answer-count").value) || 4) - 1);
  saveSettings();
});
$("#more-options").addEventListener("click", () => {
  $("#answer-count").value = Math.min(21, (Number($("#answer-count").value) || 4) + 1);
  saveSettings();
});
$$("[data-penalty]").forEach((button) => button.addEventListener("click", () => {
  $("#penalty").value = button.dataset.penalty;
  updatePresets();
  saveSettings();
}));
$("#penalty").addEventListener("input", () => { updatePresets(); saveSettings(); });
$("#answer-count").addEventListener("change", saveSettings);
$("#shuffle").addEventListener("change", saveSettings);
$("#question-limit").addEventListener("input", updateSelection);
$("#all-questions").addEventListener("change", updateSelection);
$("#previous-button").addEventListener("click", () => navigateQuestion(state.index - 1));
$("#next-button").addEventListener("click", () => {
  if (state.index === state.session.questions.length - 1) requestFinish();
  else navigateQuestion(state.index + 1);
});
$("#clear-answer").addEventListener("click", () => {
  if (state.busy) return;
  state.answers[state.session.questions[state.index].id] = [];
  renderQuestion();
  $("#quiz-title").focus({ preventScroll: true });
});
$("#finish-button").addEventListener("click", requestFinish);
$("#quit-button").addEventListener("click", () => {
  confirmAction("¿Volver a la biblioteca?", "Se perderán las respuestas de este intento. Tus cuestionarios y ajustes seguirán disponibles.", "Salir del test", () => { state.session = null; showView("setup"); loadCatalog(); });
});
$("#confirm-dialog").addEventListener("close", () => {
  const action = dialogAction;
  dialogAction = null;
  if ($("#confirm-dialog").returnValue === "confirm" && action) action();
});
$("#new-test-button").addEventListener("click", () => { state.session = null; showView("setup"); loadCatalog(); });
$("#retry-button").addEventListener("click", () => startTest(state.lastConfig));
$("#celebration-music-button").addEventListener("click", () => {
  const audio = $("#celebration-audio");
  if (audio.paused) playCelebrationMusic();
  else audio.pause();
});
for (const event of ["play", "pause", "ended"]) {
  $("#celebration-audio").addEventListener(event, () => {
    $("#celebration-music-button").textContent = $("#celebration-audio").paused ? "Reproducir música" : "Pausar música";
  });
}
$$("[data-filter]").forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.filter; renderReview(); }));
window.addEventListener("beforeunload", (event) => {
  if (state.session && !state.result) { event.preventDefault(); event.returnValue = ""; }
});
$(".brand").addEventListener("click", (event) => {
  if (state.session && !state.result) { event.preventDefault(); $("#quit-button").click(); }
});

restoreSettings();
updatePresets();
loadCatalog();
