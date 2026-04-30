const tg = window.Telegram?.WebApp;
const form = document.querySelector("#applicationForm");
const statusEl = document.querySelector("#status");
const initData = document.querySelector("#initData");
const paidAmount = document.querySelector("#paidAmount");
const expectedAmountEl = document.querySelector("#expectedAmount");
const paymentPurposeEl = document.querySelector("#paymentPurpose");
const requestFormDoc = document.querySelector("#requestFormDoc");
const payerFullName = document.querySelector("#payerFullName");
const memberSection = document.querySelector("#memberSection");
const parentConsentSection = document.querySelector("#parentConsentSection");
const memberLastName = document.querySelector("#memberLastName");
const memberFirstName = document.querySelector("#memberFirstName");
const memberMiddleName = document.querySelector("#memberMiddleName");
const motherFullName = document.querySelector("#motherFullName");
const fatherFullName = document.querySelector("#fatherFullName");
const paymentAmountValue = document.querySelector("#paymentAmountValue");
const paymentFeeLabel = document.querySelector("#paymentFeeLabel");
const paymentMemberName = document.querySelector("#paymentMemberName");
const paymentPurposeValue = document.querySelector("#paymentPurposeValue");
const jumpToReceiptButton = document.querySelector("#jumpToReceipt");
const receiptSection = document.querySelector("#receiptSection");
const birthDateInput = document.querySelector("#birthDate");
const statementDateInput = document.querySelector("#statementDate");
const signatureNamePreview = document.querySelector("#signatureNamePreview");
const roleSelect = document.querySelector("#roleSelect");
const roleOtherWrap = document.querySelector("#roleOtherWrap");
const roleOtherInput = document.querySelector("#roleOtherInput");
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
  membershipYear: 2026,
  currency: "BYN",
};
let lastSuggestedAmount = "";
let payerTouched = false;

function todayLocalIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function formatIsoDateForUser(isoDate) {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-");
  if (!year || !month || !day) return "";
  return `${day}.${month}.${year}`;
}

function normalizeDateValue(value) {
  const raw = value.trim();
  if (!raw) return "";
  const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) return raw;

  const ruMatch = raw.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!ruMatch) {
    throw new Error("Укажите дату в формате дд.мм.гггг.");
  }

  const [, dayRaw, monthRaw, year] = ruMatch;
  const day = dayRaw.padStart(2, "0");
  const month = monthRaw.padStart(2, "0");
  const iso = `${year}-${month}-${day}`;
  const parsed = new Date(`${iso}T00:00:00`);
  if (
    Number.isNaN(parsed.getTime()) ||
    parsed.getFullYear() !== Number(year) ||
    parsed.getMonth() + 1 !== Number(month) ||
    parsed.getDate() !== Number(day)
  ) {
    throw new Error("Проверьте дату: такой даты не существует.");
  }
  return iso;
}

function dateInputToIso(input) {
  if (!input?.value) return "";
  return normalizeDateValue(input.value);
}

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`;
}

function selectedFeeType() {
  return feeInputs.find((input) => input.checked)?.value || "membership";
}

function selectedFeeLabel() {
  const fee = selectedFeeType();
  if (fee === "entry") return "Вступительный";
  if (fee === "both") return "Вступительный + членский";
  return "Членский";
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

function initialsWithLastName() {
  const last = applicantNameInputs.last?.value?.trim() || "";
  const first = applicantNameInputs.first?.value?.trim() || "";
  const middle = applicantNameInputs.middle?.value?.trim() || "";
  const firstInitial = first ? `${first[0]}.` : "";
  const middleInitial = middle ? `${middle[0]}.` : "";
  return [firstInitial, middleInitial, last].filter(Boolean).join(" ").trim();
}

function fullNameForPayment() {
  if (selectedApplicantMode() === "child") {
    const memberName = [memberLastName?.value, memberFirstName?.value, memberMiddleName?.value]
      .map((value) => value?.trim())
      .filter(Boolean)
      .join(" ");
    return memberName || "Укажите Ф.И.О. ребенка";
  }
  return fullNameFromApplicant() || "Заполните заявление выше";
}

function parseBirthDate() {
  const isoDate = dateInputToIso(birthDateInput);
  if (!isoDate) return null;
  const value = new Date(`${isoDate}T00:00:00`);
  return Number.isNaN(value.getTime()) ? null : value;
}

function isMinorByBirthDate() {
  const birthDate = parseBirthDate();
  if (!birthDate) return false;
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const monthDiff = today.getMonth() - birthDate.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
    age -= 1;
  }
  return age < 18;
}

function needsParentConsent() {
  if (selectedApplicantMode() === "child") return true;
  try {
    return isMinorByBirthDate();
  } catch {
    return false;
  }
}

function syncPayerName() {
  if (payerTouched) return;
  payerFullName.value = fullNameFromApplicant();
}

function syncSignaturePreview() {
  if (!signatureNamePreview) return;
  signatureNamePreview.value = initialsWithLastName();
}

function syncPaymentPreview() {
  paymentAmountValue.textContent = String(expectedAmount());
  paymentFeeLabel.textContent = selectedFeeLabel();
  paymentMemberName.textContent = fullNameForPayment();
  paymentPurposeValue.textContent = paymentPurposeEl.textContent.replace("Назначение: ", "");
}

function syncParentConsentSection() {
  const visible = needsParentConsent();
  parentConsentSection?.classList.toggle("hidden", !visible);
  if (!visible) {
    motherFullName.value = "";
    fatherFullName.value = "";
  }
}

function syncRoleOther() {
  const isOther = roleSelect?.value === "other";
  roleOtherWrap?.classList.toggle("hidden", !isOther);
  if (roleOtherInput) {
    roleOtherInput.required = Boolean(isOther);
    if (!isOther) {
      roleOtherInput.value = "";
    }
  }
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
  syncParentConsentSection();
  syncPaymentPreview();
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

  syncPaymentPreview();
}

function validateParentConsent() {
  if (!needsParentConsent()) return true;
  if (motherFullName?.value.trim() || fatherFullName?.value.trim()) return true;
  throw new Error("Для несовершеннолетнего укажите данные хотя бы одного родителя или законного представителя.");
}

function normalizeFormDates(data) {
  const dateFields = ["birth_date", "statement_date", "payment_date"];
  for (const field of dateFields) {
    const input = form.elements[field];
    if (!input?.value) continue;
    data.set(field, normalizeDateValue(input.value));
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
    validateParentConsent();

    const data = new FormData(form);
    data.set("init_data", tg?.initData || "");
    normalizeFormDates(data);
    if (selectedApplicantMode() === "self") {
      data.set("member_last_name", "");
      data.set("member_first_name", "");
      data.set("member_middle_name", "");
    }
    if (!needsParentConsent()) {
      data.set("mother_full_name", "");
      data.set("mother_workplace_position", "");
      data.set("father_full_name", "");
      data.set("father_workplace_position", "");
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
    if (statementDateInput) {
      statementDateInput.value = formatIsoDateForUser(todayLocalIso());
    }
    syncApplicantMode();
    syncAmount();
    syncPayerName();
    syncSignaturePreview();
    syncPaymentPreview();
    syncParentConsentSection();
    syncRoleOther();
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

tg?.ready?.();
tg?.expand?.();
if (initData) {
  initData.value = tg?.initData || "";
}

if (statementDateInput && !statementDateInput.value) {
  statementDateInput.value = formatIsoDateForUser(todayLocalIso());
}

payerFullName?.addEventListener("input", () => {
  payerTouched = Boolean(payerFullName.value.trim());
});
Object.values(applicantNameInputs).forEach((input) => input?.addEventListener("input", syncPayerName));
Object.values(applicantNameInputs).forEach((input) => input?.addEventListener("input", syncPaymentPreview));
Object.values(applicantNameInputs).forEach((input) => input?.addEventListener("input", syncSignaturePreview));
memberLastName?.addEventListener("input", syncPaymentPreview);
memberFirstName?.addEventListener("input", syncPaymentPreview);
memberMiddleName?.addEventListener("input", syncPaymentPreview);
feeInputs.forEach((input) => input.addEventListener("change", syncAmount));
applicantModeInputs.forEach((input) => input.addEventListener("change", syncApplicantMode));
birthDateInput?.addEventListener("change", syncParentConsentSection);
roleSelect?.addEventListener("change", syncRoleOther);
requestFormDoc?.addEventListener("click", requestFormDocument);
jumpToReceiptButton?.addEventListener("click", () => {
  receiptSection?.scrollIntoView({ behavior: "smooth", block: "start" });
});
form.addEventListener("submit", submitForm);

syncApplicantMode();
syncPayerName();
syncSignaturePreview();
syncPaymentPreview();
syncParentConsentSection();
syncRoleOther();
loadConfig().catch(() => setStatus("Не удалось загрузить настройки формы.", "error"));
