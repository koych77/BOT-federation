const tg = window.Telegram?.WebApp;
const form = document.querySelector("#applicationForm");
const statusEl = document.querySelector("#status");
const initData = document.querySelector("#initData");
const paidAmount = document.querySelector("#paidAmount");
const expectedAmountEl = document.querySelector("#expectedAmount");
const paymentPurposeEl = document.querySelector("#paymentPurpose");
const feeInputs = [...document.querySelectorAll("input[name='fee_type']")];

let config = {
  entryFee: 45,
  membershipFee: 90,
  currency: "BYN",
};
let lastSuggestedAmount = "";

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`;
}

function expectedAmount() {
  const fee = feeInputs.find((input) => input.checked)?.value;
  if (fee === "entry") return config.entryFee;
  if (fee === "both") return config.entryFee + config.membershipFee;
  return config.membershipFee;
}

function syncAmount() {
  const amount = expectedAmount();
  paidAmount.placeholder = String(amount);
  if (!paidAmount.value || paidAmount.value === lastSuggestedAmount) {
    paidAmount.value = String(amount);
  }
  lastSuggestedAmount = String(amount);
  expectedAmountEl.textContent = String(amount);
  const fee = feeInputs.find((input) => input.checked)?.value;
  const year = config.membershipYear || 2026;
  if (fee === "entry") {
    paymentPurposeEl.textContent = `Назначение: вступительный взнос за ${year} год.`;
  } else if (fee === "both") {
    paymentPurposeEl.textContent = `Назначение: вступительный и членский взносы за ${year} год.`;
  } else {
    paymentPurposeEl.textContent = `Назначение: членский взнос за ${year} год.`;
  }
}

async function loadConfig() {
  const response = await fetch("/api/config");
  config = await response.json();
  document.querySelector("#entryFee").textContent = config.entryFee;
  document.querySelector("#membershipFee").textContent = config.membershipFee;
  syncAmount();
}

async function submitForm(event) {
  event.preventDefault();
  setStatus("");
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;

  try {
    const data = new FormData(form);
    data.set("init_data", tg?.initData || "");
    const response = await fetch("/api/applications", {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Не удалось отправить заявку.");
    }
    const checkText = payload.autoCheckStatus ? ` Статус автопроверки: ${payload.autoCheckStatus}.` : "";
    setStatus(`${payload.message}${checkText}`, "ok");
    tg?.MainButton?.hide();
    tg?.HapticFeedback?.notificationOccurred?.("success");
    form.reset();
    syncAmount();
  } catch (error) {
    setStatus(error.message, "error");
    tg?.HapticFeedback?.notificationOccurred?.("error");
  } finally {
    button.disabled = false;
  }
}

tg?.ready?.();
tg?.expand?.();
if (initData) {
  initData.value = tg?.initData || "";
}

feeInputs.forEach((input) => input.addEventListener("change", syncAmount));
form.addEventListener("submit", submitForm);
loadConfig().catch(() => setStatus("Не удалось загрузить настройки формы.", "error"));
