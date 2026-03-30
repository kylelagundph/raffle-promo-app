/* ============================================================
   Raffle Promotion App — Frontend JS
   ============================================================ */

const API_BASE = '';

// ── DOM refs ──────────────────────────────────────────────────
const form          = document.getElementById('entryForm');
const submitBtn     = document.getElementById('submitBtn');
const globalAlert   = document.getElementById('globalAlert');
const uploadArea    = document.getElementById('uploadArea');
const receiptInput  = document.getElementById('receipt');
const previewImg    = document.getElementById('previewImg');
const uploadPreview = document.getElementById('uploadPreview');
const uploadFilename= document.getElementById('uploadFilename');
const successState  = document.getElementById('successState');
const formCard      = document.getElementById('formCard');
const footerYear    = document.getElementById('footerYear');

if (footerYear) footerYear.textContent = new Date().getFullYear();

// ── Load promo settings ───────────────────────────────────────
async function loadSettings() {
  try {
    const r = await fetch(`${API_BASE}/api/settings`);
    if (!r.ok) return;
    const s = await r.json();

    if (s.promo_title) {
      document.title = s.promo_title + ' 🇰🇷';
      const h1 = document.querySelector('.hero-content h1');
      if (h1) h1.innerHTML = s.promo_title.replace('Korea', '<span class="korea-text">Korea!</span>');
    }
    if (s.campaign_start_date && s.campaign_end_date) {
      const start = formatDate(s.campaign_start_date);
      const end   = formatDate(s.campaign_end_date);
      const el = document.getElementById('heroDates');
      if (el) el.textContent = `🗓️ ${start} – ${end}`;
      const period = document.getElementById('promoPeriod');
      if (period) period.textContent = `${start} – ${end}`;

      // Set date picker min/max
      const dp = document.getElementById('purchase_date');
      if (dp) {
        dp.min = s.campaign_start_date;
        dp.max = s.campaign_end_date;
      }
    }
    if (s.prize_description) {
      const el = document.getElementById('heroPrize');
      if (el) el.textContent = `🎁 ${s.prize_description}`;
      const desc = document.getElementById('prizeDesc');
      if (desc) desc.textContent = s.prize_description;
    }
    if (s.draw_date) {
      const el = document.getElementById('drawDateDisplay');
      if (el) el.textContent = formatDate(s.draw_date);
    }
  } catch (e) {
    // Settings API not available — defaults already in HTML
  }
}

function formatDate(isoStr) {
  try {
    return new Date(isoStr + 'T00:00:00').toLocaleDateString('en-PH', {
      day: 'numeric', month: 'long', year: 'numeric'
    });
  } catch { return isoStr; }
}

loadSettings();

// ── Phone prefix ──────────────────────────────────────────────
// Phone field has visible +63 prefix — submit as +63XXXXXXXXXX
function getFullPhone() {
  const digits = document.getElementById('phone')?.value.replace(/\D/g, '') || '';
  return '+63' + digits;
}

// ── Upload area ───────────────────────────────────────────────
if (uploadArea) {
  uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
  uploadArea.addEventListener('drop', e => {
    e.preventDefault(); uploadArea.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length) { receiptInput.files = files; handleFileSelect(files[0]); }
  });
  uploadArea.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); receiptInput.click(); } });
  receiptInput.addEventListener('change', e => { if (e.target.files.length) handleFileSelect(e.target.files[0]); });
}

function handleFileSelect(file) {
  const ALLOWED = ['image/jpeg', 'image/png', 'image/heic', 'image/heif'];
  if (!ALLOWED.includes(file.type) && !file.name.match(/\.(heic|heif)$/i)) {
    showReceiptError('Only JPG, PNG, or HEIC files are allowed.'); return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showReceiptError('File too large. Maximum 10 MB.'); return;
  }
  const reader = new FileReader();
  reader.onload = ev => {
    previewImg.src = ev.target.result;
    uploadPreview.style.display = 'block';
    uploadFilename.textContent = `${file.name} (${(file.size/1024/1024).toFixed(2)} MB)`;
    uploadArea.classList.add('has-file');
    hideReceiptError();
  };
  reader.readAsDataURL(file);
}

function showReceiptError(msg) {
  const fb = document.getElementById('receiptFeedback');
  if (fb) { fb.textContent = msg; fb.style.display = 'block'; }
  uploadArea.classList.add('is-invalid');
}
function hideReceiptError() {
  const fb = document.getElementById('receiptFeedback');
  if (fb) fb.style.display = 'none';
  uploadArea.classList.remove('is-invalid');
}

// ── Invoice number: digits only ───────────────────────────────
const invoiceInput = document.getElementById('invoice_number');
if (invoiceInput) {
  invoiceInput.addEventListener('input', () => {
    invoiceInput.value = invoiceInput.value.replace(/\D/g, '').slice(0, 10);
  });
}

// ── Steps indicator ───────────────────────────────────────────
function updateSteps() {
  const name    = document.getElementById('name')?.value.trim();
  const email   = document.getElementById('email')?.value.trim();
  const phone   = document.getElementById('phone')?.value.trim();
  const invoice = document.getElementById('invoice_number')?.value.trim();
  const date_v  = document.getElementById('purchase_date')?.value.trim();
  const file    = receiptInput?.files[0];

  if (name && email && phone && invoice && date_v) {
    document.getElementById('step1')?.classList.add('done');
    document.getElementById('step2')?.classList.add('active');
  }
  if (file) {
    document.getElementById('step2')?.classList.add('done');
  }
}

['name','email','phone','invoice_number','purchase_date'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', updateSteps);
});

// ── Form submit ───────────────────────────────────────────────
if (form) {
  form.addEventListener('submit', async e => {
    e.preventDefault();
    hideAlert();

    // Validate invoice
    const invoiceVal = invoiceInput?.value.trim() || '';
    if (!/^\d{10}$/.test(invoiceVal)) {
      document.getElementById('invoiceFeedback').textContent = 'Invoice/OR number must be exactly 10 digits.';
      invoiceInput?.classList.add('is-invalid');
      return;
    } else {
      invoiceInput?.classList.remove('is-invalid');
    }

    // Validate receipt file
    if (!receiptInput?.files[0]) {
      showReceiptError('Please upload your receipt.'); return;
    }

    // Validate date
    const dateVal = document.getElementById('purchase_date')?.value;
    if (!dateVal) {
      document.getElementById('dateFeedback').textContent = 'Please select your purchase date.';
      document.getElementById('purchase_date')?.classList.add('is-invalid');
      return;
    }

    setLoading(true);

    const fd = new FormData();
    fd.append('name',           document.getElementById('name').value.trim());
    fd.append('email',          document.getElementById('email').value.trim());
    fd.append('phone',          getFullPhone());
    fd.append('purchase_date',  dateVal);
    fd.append('invoice_number', invoiceVal);
    fd.append('consent',        document.getElementById('consent').checked ? 'true' : 'false');
    fd.append('receipt',        receiptInput.files[0]);

    try {
      const r = await fetch(`${API_BASE}/api/submit`, { method: 'POST', body: fd });
      const data = await r.json();

      if ((r.ok || r.status === 202) && data.success) {
        // Success
        document.getElementById('step2')?.classList.add('done');
        document.getElementById('step3')?.classList.add('active', 'done');
        form.style.display = 'none';
        successState.style.display = 'block';
        if (data.entry_id) {
          document.getElementById('successEntryId').textContent = `Entry ID: ${data.entry_id}`;
        }
      } else {
        showAlert(data.detail || 'Something went wrong. Please try again.', 'error');
      }
    } catch (err) {
      showAlert('Network error. Please check your connection and try again.', 'error');
    } finally {
      setLoading(false);
    }
  });
}

function setLoading(loading) {
  if (!submitBtn) return;
  submitBtn.disabled = loading;
  submitBtn.querySelector('.btn-text').textContent = loading ? 'Submitting…' : 'Enter Now 🇰🇷';
  submitBtn.querySelector('.spinner').style.display = loading ? 'inline-block' : 'none';
}

function showAlert(msg, type = 'error') {
  if (!globalAlert) return;
  globalAlert.textContent = msg;
  globalAlert.className = `alert alert-${type}`;
  globalAlert.style.display = 'block';
  globalAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideAlert() {
  if (globalAlert) globalAlert.style.display = 'none';
}
