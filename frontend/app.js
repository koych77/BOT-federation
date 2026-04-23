const tg = window.Telegram?.WebApp;
const form = document.querySelector("#applicationForm");
const statusEl = document.querySelector("#status");
const initData = document.querySelector("#initData");
const paidAmount = document.querySelector("#paidAmount");
const expectedAmountEl = document.querySelector("#expectedAmount");
const paymentPurposeEl = document.querySelector("#paymentPurpose");
const requestFormDoc = document.querySelector("#requestFormDoc");
const copyEripPathButton = document.querySelector("#copyEripPath");
const payerFullName = document.querySelector("#payerFullName");
const memberSection = document.querySelector("#memberSection");
const memberLastName = document.querySelector("#memberLastName");
const memberFirstName = document.querySelector("#memberFirstName");
const memberMiddleName = document.querySelector("#memberMiddleName");
const applicantModeInputs = [...document.querySelectorAll("input[name='applicant_mode']")];
const feeInputs = [...document.querySelectorAll("input[name='fee_type']")];
const applicantNameInputs = {
  last: document.querySelector("input[name='applicant_last_name']"),
  first: document.querySelector("input[name='applicant_first_name']"),
  middle: document.querySelector("input[name='applicant_middle_name']"),
};

let config = {
  entryFee: 45,
  membershipFee: 90,
  currency: "BYN",
};
let lastSuggestedAmount = "";
let payerTouched = false;
const eripPathText = [
  "Путь ЕРИП:",
  "1. Благотворительность, общественные объединения",
  "2. Прочие общественные объединения",
  "3. Бел. федерация брейкинга",
  "Указывайте Ф.И.О. за кого оплата.",
].join("\n");

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`;
}

function selectedFeeType() {
  return feeInputs.find((input) => input.checked)?.value || "membership";
}

function selectedApplicantMode() {
  return applicantModeInputs.find((input) => input.checked)?.value || "self";
}

function expectedAmount() {
  const fee = selectedFeeType();
  if (fee === "entry") return config.entryFee;
  if (fee === "both") return config.entryFee + config.membershipFee;
  return config.membershipFee;
}

function fullNameFromApplicant() {
  return [applicantNameInputs.last?.value, applicantNameInputs.first?.value, applicantNameInputs.middle?.value]
    .map((value) => value?.trim())
    .filter(Boolean)
    .join(" ");
}

function syncPayerName() {
  if (payerTouched) return;
  payerFullName.value = fullNameFromApplicant();
}

function syncApplicantMode() {
  const isChild = selectedApplicantMode() === "child";
  memberSection?.classList.toggle("hidden", !isChild);
  memberLastName.required = isChild;
  memberFirstName.required = isChild;
  memberMiddleName.required = false;
  if (!isChild) {
    memberLastName.value = "";
    memberFirstName.value = "";
    memberMiddleName.value = "";
  }
}

function syncAmount() {
  const amount = expectedAmount();
  paidAmount.placeholder = String(amount);
  if (!paidAmount.value || paidAmount.value === lastSuggestedAmount) {
    paidAmount.value = String(amount);
  }
  lastSuggestedAmount = String(amount);
  expectedAmountEl.textContent = String(amount);

  const fee = selectedFeeType();
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
    if (selectedApplicantMode() === "self") {
      data.set("member_last_name", "");
      data.set("member_first_name", "");
      data.set("member_middle_name", "");
    }

    const response = await fetch("/api/applications", {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Не удалось отправить заявление.");
    }

    const checkText = payload.autoCheckStatus ? ` Статус автопроверки: ${payload.autoCheckStatus}.` : "";
    setStatus(`${payload.message}${checkText}`, "ok");
    tg?.MainButton?.hide();
    tg?.HapticFeedback?.notificationOccurred?.("success");
    form.reset();
    payerTouched = false;
    syncApplicantMode();
    syncAmount();
    syncPayerName();
  } catch (error) {
    setStatus(error.message, "error");
    tg?.HapticFeedback?.notificationOccurred?.("error");
  } finally {
    button.disabled = false;
  }
}

async function requestFormDocument() {
  if (!requestFormDoc) return;
  const originalText = requestFormDoc.textContent;
  requestFormDoc.disabled = true;
  requestFormDoc.textContent = "Отправляем бланк...";
  try {
    const response = await fetch("/api/request-form-doc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initData: tg?.initData || "" }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Не удалось отправить бланк.");
    }
    setStatus(payload.message, "ok");
    tg?.HapticFeedback?.notificationOccurred?.("success");
  } catch (error) {
    setStatus(error.message, "error");
    tg?.HapticFeedback?.notificationOccurred?.("error");
  } finally {
    requestFormDoc.disabled = false;
    requestFormDoc.textContent = originalText;
  }
}

async function copyEripPath() {
  try {
    await navigator.clipboard.writeText(eripPathText);
    setStatus("Путь ЕРИП скопирован.", "ok");
    tg?.HapticFeedback?.notificationOccurred?.("success");
  } catch {
    setStatus("Не удалось скопировать путь ЕРИП. Скопируйте его вручную с экрана.", "error");
    tg?.HapticFeedback?.notificationOccurred?.("error");
  }
}

tg?.ready?.();
tg?.expand?.();
if (initData) {
  initData.value = tg?.initData || "";
}

payerFullName?.addEventListener("input", () => {
  payerTouched = Boolean(payerFullName.value.trim());
});
Object.values(applicantNameInputs).forEach((input) => input?.addEventListener("input", syncPayerName));
feeInputs.forEach((input) => input.addEventListener("change", syncAmount));
applicantModeInputs.forEach((input) => input.addEventListener("change", syncApplicantMode));
requestFormDoc?.addEventListener("click", requestFormDocument);
copyEripPathButton?.addEventListener("click", copyEripPath);
form.addEventListener("submit", submitForm);

syncApplicantMode();
syncPayerName();
loadConfig().catch(() => setStatus("Не удалось загрузить настройки формы.", "error"));
