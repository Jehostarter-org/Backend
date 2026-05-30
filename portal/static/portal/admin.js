const Portal = (() => {
  const TOKEN_KEY = 'jeho_admin_access';
  const REFRESH_KEY = 'jeho_admin_refresh';
  const USER_KEY = 'jeho_admin_user';

  const apiBase = window.location.origin;

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setSession(tokens, user) {
    localStorage.setItem(TOKEN_KEY, tokens.access);
    localStorage.setItem(REFRESH_KEY, tokens.refresh);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getUser() {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  function showError(el, message) {
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden');
  }

  function hideError(el) {
    if (!el) el.classList.add('hidden');
  }

  function flattenErrors(data) {
    if (!data) return 'Something went wrong.';
    if (typeof data === 'string') return data;
    if (data.detail) return data.detail;
    return Object.entries(data)
      .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
      .join(' ');
  }

  async function refreshAccessToken() {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!refresh) throw new Error('Session expired');

    const response = await fetch(`${apiBase}/api/users/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) throw new Error('Session expired');
    const data = await response.json();
    localStorage.setItem(TOKEN_KEY, data.access);
    return data.access;
  }

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    let token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    let response = await fetch(`${apiBase}${path}`, { ...options, headers });

    if (response.status === 401 && localStorage.getItem(REFRESH_KEY)) {
      token = await refreshAccessToken();
      headers.Authorization = `Bearer ${token}`;
      response = await fetch(`${apiBase}${path}`, { ...options, headers });
    }

    const contentType = response.headers.get('content-Type') || '';
    const data = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const error = new Error(flattenErrors(data));
      error.data = data;
      error.status = response.status;
      throw error;
    }

    return data;
  }

  function requireAuth() {
    if (!getToken()) {
      window.location.href = '/portal/login/';
    }
  }

  function initShell() {
    const user = getUser();
    const userEl = document.getElementById('admin-user');
    if (userEl && user) {
      userEl.textContent = `${user.first_name || user.username} · ${user.email}`;
    }

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        clearSession();
        window.location.href = '/portal/login/';
      });
    }
  }

  async function initLoginPage() {
    if (getToken()) {
      window.location.href = '/portal/shops/';
      return;
    }

    const form = document.getElementById('login-form');
    const errorEl = document.getElementById('login-error');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorEl.classList.add('hidden');

      const formData = new FormData(form);
      const payload = {
        username: formData.get('username'),
        password: formData.get('password'),
      };

      try {
        const tokens = await api('/api/users/admin/login/', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        const profileResponse = await fetch(`${apiBase}/api/users/admin/me/`, {
          headers: { Authorization: `Bearer ${tokens.access}` },
        });
        const profile = await profileResponse.json();
        if (!profileResponse.ok) {
          throw new Error(profile.detail || 'Could not verify admin access.');
        }

        setSession(tokens, profile);
        window.location.href = '/portal/shops/';
      } catch (error) {
        showError(errorEl, error.message);
      }
    });
  }

  async function initRegisterPage() {
    if (getToken()) {
      window.location.href = '/portal/shops/';
      return;
    }

    const form = document.getElementById('register-form');
    const errorEl = document.getElementById('register-error');
    const successEl = document.getElementById('register-success');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorEl.classList.add('hidden');
      successEl.classList.add('hidden');

      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());

      try {
        await api('/api/users/admin/register/', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        successEl.textContent = 'Admin account created. You can sign in now.';
        successEl.classList.remove('hidden');
        form.reset();
      } catch (error) {
        showError(errorEl, error.message);
      }
    });
  }

  async function initDashboardPage() {
    try {
      const stats = await api('/api/shops/admin/shops/stats/');
      document.getElementById('stat-pending').textContent = stats.shops.pending_approval;
      document.getElementById('stat-active').textContent = stats.shops.active;
      document.getElementById('stat-rejected').textContent = stats.shops.rejected;
      document.getElementById('stat-changes').textContent = stats.shops.changes_requested;
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
      }
    }
  }

  let activeShopId = null;

  function renderShopCard(shop) {
    return `
      <article class="shop-card">
        <div class="shop-card-header">
          <div>
            <h3>${escapeHtml(shop.name)}</h3>
            <div class="shop-meta">
              ${escapeHtml(shop.owner_name || 'Unknown owner')} · ${escapeHtml(shop.owner_email || '')}
              ${shop.city ? ` · ${escapeHtml(shop.city)}` : ''}
            </div>
          </div>
          <span class="status-pill status-${shop.approval_status || 'pending'}">${escapeHtml(shop.approval_status || 'pending')}</span>
        </div>
        <div class="shop-meta">${shop.documents_count || 0} document(s) uploaded · submitted ${formatDate(shop.created_at)}</div>
        <div class="shop-card-actions">
          <button class="btn btn-secondary" data-action="view" data-id="${shop.id}">View details</button>
          <button class="btn btn-primary" data-action="approve" data-id="${shop.id}">Approve</button>
          <button class="btn btn-danger" data-action="reject" data-id="${shop.id}">Reject</button>
        </div>
      </article>
    `;
  }

  async function loadPendingShops() {
    const loadingEl = document.getElementById('shops-loading');
    const emptyEl = document.getElementById('shops-empty');
    const listEl = document.getElementById('shops-list');
    const errorEl = document.getElementById('shops-error');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const data = await api('/api/shops/admin/shops/pending/');
      const shops = Array.isArray(data) ? data : (data.results || []);
      loadingEl.classList.add('hidden');

      if (!shops.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = shops.map(renderShopCard).join('');
      bindShopActions();
    } catch (error) {
      loadingEl.classList.add('hidden');
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
        return;
      }
      showError(errorEl, error.message);
    }
  }

  function bindShopActions() {
    document.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const shopId = button.dataset.id;
        const action = button.dataset.action;

        if (action === 'view') {
          await openShopModal(shopId);
          return;
        }

        if (action === 'approve') {
          await processShop(shopId, 'approve');
          return;
        }

        if (action === 'reject') {
          const reason = window.prompt('Rejection reason:');
          if (!reason) return;
          await processShop(shopId, 'reject', reason);
        }
      });
    });
  }

  async function openShopModal(shopId) {
    activeShopId = shopId;
    const modal = document.getElementById('shop-modal');
    const body = document.getElementById('modal-body');
    const notes = document.getElementById('modal-notes');

    notes.value = '';
    body.innerHTML = '<div class="loading">Loading shop details…</div>';
    modal.showModal();

    try {
      const shop = await api(`/api/shops/admin/shops/${shopId}/approval-detail/`);
      document.getElementById('modal-shop-name').textContent = shop.name;
      document.getElementById('modal-shop-meta').textContent =
        `${shop.owner?.name || ''} · ${shop.owner?.email || ''}`;

      const approval = shop.approval_request || {};
      const documents = shop.documents || [];

      body.innerHTML = `
        <div class="detail-grid">
          <div class="detail-block"><strong>Business name</strong>${escapeHtml(approval.business_name || '—')}</div>
          <div class="detail-block"><strong>Registration #</strong>${escapeHtml(approval.registration_number || '—')}</div>
          <div class="detail-block"><strong>Tax number</strong>${escapeHtml(approval.tax_number || '—')}</div>
          <div class="detail-block"><strong>Phone</strong>${escapeHtml(approval.business_phone || '—')}</div>
          <div class="detail-block"><strong>Email</strong>${escapeHtml(approval.business_email || '—')}</div>
          <div class="detail-block"><strong>Status</strong>${escapeHtml(approval.status || '—')}</div>
        </div>
        <div class="detail-block" style="margin-bottom:20px">
          <strong>Business address</strong>
          ${escapeHtml(approval.business_address || '—')}
        </div>
        <div class="detail-block" style="margin-bottom:20px">
          <strong>Description</strong>
          ${escapeHtml(approval.business_description || shop.description || '—')}
        </div>
        <h3>Documents</h3>
        <div class="doc-list">
          ${documents.length ? documents.map((doc) => `
            <div class="doc-item">
              <div>
                <strong>${escapeHtml(doc.document_type_display || doc.document_type)}</strong>
                <div class="shop-meta">${escapeHtml(doc.document_name || '')}</div>
              </div>
              ${doc.document_url ? `<a href="${doc.document_url}" target="_blank" rel="noopener">Open file</a>` : ''}
            </div>
          `).join('') : '<p class="shop-meta">No documents uploaded.</p>'}
        </div>
      `;
    } catch (error) {
      body.innerHTML = `<div class="alert alert-error">${escapeHtml(error.message)}</div>`;
    }
  }

  async function processShop(shopId, action, notes = '') {
    const payload = { action };
    if (notes) payload.notes = notes;

    await api(`/api/shops/admin/shops/${shopId}/process-approval/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    const modal = document.getElementById('shop-modal');
    if (modal.open) modal.close();

    await loadPendingShops();
  }

  function initShopsPage() {
    const modal = document.getElementById('shop-modal');
    document.getElementById('refresh-shops').addEventListener('click', loadPendingShops);
    document.getElementById('modal-close').addEventListener('click', () => modal.close());
    document.getElementById('modal-approve').addEventListener('click', async () => {
      if (!activeShopId) return;
      const notes = document.getElementById('modal-notes').value.trim();
      await processShop(activeShopId, 'approve', notes);
    });
    document.getElementById('modal-reject').addEventListener('click', async () => {
      if (!activeShopId) return;
      const notes = document.getElementById('modal-notes').value.trim();
      if (!notes) {
        alert('Please enter a rejection reason in the notes field.');
        return;
      }
      await processShop(activeShopId, 'reject', notes);
    });

    loadPendingShops();
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
  }

  function formatDate(value) {
    if (!value) return 'recently';
    return new Date(value).toLocaleString();
  }

  return {
    requireAuth,
    initShell,
    initLoginPage,
    initRegisterPage,
    initDashboardPage,
    initShopsPage,
  };
})();
