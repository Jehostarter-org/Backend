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

  async function initDashboardProviderStats() {
    try {
      const stats = await api('/api/services/admin/providers/stats/');
      document.getElementById('stat-provider-pending').textContent = stats.providers.pending_approval;
      document.getElementById('stat-provider-approved').textContent = stats.providers.approved;
      document.getElementById('stat-provider-rejected').textContent = stats.providers.rejected;
      document.getElementById('stat-provider-pending-drivers').textContent = stats.by_service_type.pending_drivers;
      document.getElementById('stat-provider-pending-chaperones').textContent = stats.by_service_type.pending_chaperones;
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
      }
    }
  }

  let activeItemId = null;
  let activeItemTitle = '';

  function renderItemCard(item) {
    const img = item.primary_image
      ? `<img src="${escapeHtml(item.primary_image)}" alt="" style="width:56px;height:56px;object-fit:cover;border-radius:8px;flex-shrink:0;" onerror="this.style.display='none'"/>`
      : '<div style="width:56px;height:56px;border-radius:8px;background:#eef2f7;flex-shrink:0;"></div>';
    const available = Boolean(item.is_available);
    return `
      <article class="shop-card">
        <div class="shop-card-header" style="display:flex;gap:14px;align-items:flex-start;">
          ${img}
          <div style="min-width:0;">
            <h3>${escapeHtml(item.title)}</h3>
            <div class="shop-meta">
              ${escapeHtml(item.shop_name || '')} · ${escapeHtml(item.owner_name || 'Unknown owner')}
              ${item.owner_email ? ` · ${escapeHtml(item.owner_email)}` : ''}
            </div>
          </div>
        </div>
        <div class="shop-meta">
          <strong>${escapeHtml(item.currency || '')}${item.price}</strong>
          ${item.category_name ? ` · ${escapeHtml(item.category_name)}` : ''}
          ${item.is_boosted ? ' · <span style="color:#d97706;">Boosted</span>' : ''}
          · ${item.image_count || 0} image(s) · listed ${formatDate(item.created_at)}
        </div>
        <div class="shop-card-actions" style="justify-content:space-between;">
          <span class="status-pill ${available ? 'status-approved' : 'status-rejected'}">${available ? 'Available' : 'Unavailable'}</span>
          <button class="btn btn-danger" data-action="delete" data-id="${item.id}" data-title="${escapeHtml(item.title)}">Delete</button>
        </div>
      </article>
    `;
  }

  async function loadShopItems() {
    const loadingEl = document.getElementById('items-loading');
    const emptyEl = document.getElementById('items-empty');
    const listEl = document.getElementById('items-list');
    const errorEl = document.getElementById('items-error');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const q = document.getElementById('item-search').value.trim();
      const status = document.getElementById('item-status-filter').value;
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (status) params.set('status', status);
      const qs = params.toString();
      const data = await api('/api/shops/admin/items/' + (qs ? `?${qs}` : ''));
      const items = Array.isArray(data) ? data : (data.results || []);

      const allData = await api('/api/shops/admin/items/');
      const allItems = Array.isArray(allData) ? allData : (allData.results || []);
      document.getElementById('item-stat-total').textContent = allItems.length;
      document.getElementById('item-stat-active').textContent = allItems.filter((i) => i.is_available).length;
      document.getElementById('item-stat-inactive').textContent = allItems.filter((i) => !i.is_available).length;
      document.getElementById('item-stat-boosted').textContent = allItems.filter((i) => i.is_boosted).length;

      loadingEl.classList.add('hidden');
      if (!items.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = items.map(renderItemCard).join('');
      bindItemActions();
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

  function bindItemActions() {
    document.querySelectorAll('[data-action="delete"]').forEach((button) => {
      button.addEventListener('click', () => {
        activeItemId = button.dataset.id;
        activeItemTitle = button.dataset.title || 'this item';
        document.getElementById('delete-item-meta').textContent = `"${activeItemTitle}"`;
        document.getElementById('item-delete-modal').showModal();
      });
    });
  }

  async function deleteItem() {
    if (!activeItemId) return;
    try {
      await api(`/api/shops/admin/items/${activeItemId}/`, { method: 'DELETE' });
      document.getElementById('item-delete-modal').close();
      activeItemId = null;
      await loadShopItems();
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
        return;
      }
      alert(error.message || 'Failed to delete item.');
    }
  }

  function initShopItemsPage() {
    document.getElementById('refresh-items').addEventListener('click', loadShopItems);
    document.getElementById('item-search').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loadShopItems();
    });
    document.getElementById('item-status-filter').addEventListener('change', loadShopItems);
    const modal = document.getElementById('item-delete-modal');
    document.getElementById('delete-close').addEventListener('click', () => modal.close());
    document.getElementById('delete-cancel').addEventListener('click', () => modal.close());
    document.getElementById('delete-confirm').addEventListener('click', deleteItem);
    loadShopItems();
  }

  async function loadUsers() {
    const loadingEl = document.getElementById('users-loading');
    const emptyEl = document.getElementById('users-empty');
    const listEl = document.getElementById('users-list');
    const errorEl = document.getElementById('users-error');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const data = await api('/api/users/admin/users/');
      const users = data.results || data || [];
      loadingEl.classList.add('hidden');

      if (!users.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = users.map(renderUserCard).join('');
      bindUserActions();
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

  function renderUserCard(user) {
    const plan = user.membership_plan ? user.membership_plan.toUpperCase() : 'FREE';
    const statusText = user.is_verified ? 'Verified' : 'Unverified';
    const statusClass = user.is_verified ? 'success' : 'pending';
    const activeStatus = user.is_active !== false;
    
    return `
      <article class="shop-card">
        <div class="shop-card-header">
          <div>
            <h3>${escapeHtml(user.first_name || '')} ${escapeHtml(user.last_name || '')} <span class="shop-meta">(@${escapeHtml(user.username)})</span></h3>
            <div class="shop-meta">
              ${escapeHtml(user.email)} · plan: <strong>${escapeHtml(plan)}</strong>
            </div>
          </div>
          <div style="display:flex; gap:6px; align-items:center;">
            <span class="status-pill status-${statusClass}">${escapeHtml(statusText)}</span>
            ${!activeStatus ? '<span class="status-pill" style="background:rgba(239,68,68,0.12); color:#dc2626; border:1px solid rgba(239,68,68,0.25);">Suspended</span>' : ''}
          </div>
        </div>
        <div class="shop-meta">
          Location: ${escapeHtml(user.city || 'Not set')}, ${escapeHtml(user.current_country || 'Not set')} · Joined ${formatDate(user.created_at)}
        </div>
        <div class="shop-card-actions">
          <button class="btn btn-secondary" data-action="view-user" data-id="${user.id}">View full details</button>
          <button class="btn ${activeStatus ? 'btn-danger' : 'btn-primary'}" data-action="toggle-user-active" data-id="${user.id}" data-active="${activeStatus}">
            ${activeStatus ? 'Suspend' : 'Unsuspend'}
          </button>
        </div>
      </article>
    `;
  }

  function bindUserActions() {
    document.querySelectorAll('[data-action="view-user"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const userId = button.dataset.id;
        await openUserModal(userId);
      });
    });
    document.querySelectorAll('[data-action="toggle-user-active"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const userId = button.dataset.id;
        const isActive = button.dataset.active === 'true';
        const action = isActive ? 'suspend' : 'unsuspend';
        if (!confirm(`Are you sure you want to ${action} this user?`)) return;
        await toggleUserActive(userId);
      });
    });
  }

  async function toggleUserActive(userId) {
    await api(`/api/users/admin/users/${userId}/toggle-active/`, {
      method: 'POST',
    });
    await loadUsers();
  }

  async function openUserModal(userId) {
    const modal = document.getElementById('user-modal');
    const body = document.getElementById('modal-body');
    
    body.innerHTML = '<div class="loading">Loading user details…</div>';
    modal.showModal();

    try {
      const user = await api(`/api/users/admin/users/${userId}/`);
      document.getElementById('modal-user-name').textContent = `${user.first_name || ''} ${user.last_name || ''}`;
      document.getElementById('modal-user-meta').textContent = `@${user.username} · ${user.email}`;

      body.innerHTML = `
        <div class="detail-grid">
          <div class="detail-block"><strong>Username</strong>@${escapeHtml(user.username || '—')}</div>
          <div class="detail-block"><strong>Email</strong>${escapeHtml(user.email || '—')}</div>
          <div class="detail-block"><strong>Phone</strong>${escapeHtml(user.phone || '—')}</div>
          <div class="detail-block"><strong>Joined</strong>${formatDate(user.created_at)}</div>
          <div class="detail-block"><strong>Verification status</strong>${user.is_verified ? 'Verified ✓' : 'Unverified ✗'}</div>
          <div class="detail-block"><strong>Account status</strong>${user.is_active !== false ? '<span style="color:#10b981;">Active ✓</span>' : '<span style="color:#dc2626;">Suspended ✗</span>'}</div>
          <div class="detail-block"><strong>Membership plan</strong>${escapeHtml(user.membership_plan?.toUpperCase() || 'FREE')}</div>
        </div>
        
        <h3 style="margin-top:20px; margin-bottom:12px;">Migration Details</h3>
        <div class="detail-grid">
          <div class="detail-block"><strong>Migration status</strong>${escapeHtml(user.migration_status || '—')}</div>
          <div class="detail-block"><strong>Birth country</strong>${escapeHtml(user.birth_country || '—')}</div>
          <div class="detail-block"><strong>Current country</strong>${escapeHtml(user.current_country || '—')}</div>
          <div class="detail-block"><strong>Destination country</strong>${escapeHtml(user.destination_country || '—')}</div>
          <div class="detail-block"><strong>City</strong>${escapeHtml(user.city || '—')}</div>
          <div class="detail-block"><strong>State/Province</strong>${escapeHtml(user.state_province || '—')}</div>
        </div>

        <h3 style="margin-top:20px; margin-bottom:12px;">Bio & Agreement</h3>
        <div class="detail-block" style="margin-bottom:16px;">
          <strong>Personal Bio</strong>
          <p style="margin: 0; white-space: pre-wrap;">${escapeHtml(user.bio || 'No bio provided.')}</p>
        </div>
        <div class="detail-block">
          <strong>Terms Acceptance</strong>
          Accepted: ${user.accepted_terms ? 'Yes ✓' : 'No ✗'} ${user.accepted_terms_at ? `on ${formatDate(user.accepted_terms_at)}` : ''}
        </div>

        ${user.id ? `
        <div style="margin-top:20px; padding-top:16px; border-top:1px solid #e5e7eb;">
          <button class="btn ${user.is_active !== false ? 'btn-danger' : 'btn-primary'}" id="modal-toggle-active"
            data-id="${user.id}" data-active="${user.is_active !== false}">
            ${user.is_active !== false ? 'Suspend Account' : 'Unsuspend Account'}
          </button>
        </div>
        ` : ''}
      `;

      const toggleBtn = document.getElementById('modal-toggle-active');
      if (toggleBtn) {
        toggleBtn.addEventListener('click', async () => {
          const uid = toggleBtn.dataset.id;
          const isActive = toggleBtn.dataset.active === 'true';
          const act = isActive ? 'suspend' : 'unsuspend';
          if (!confirm(`Are you sure you want to ${act} this user?`)) return;
          await toggleUserActive(uid);
          modal.close();
        });
      }
    } catch (error) {
      body.innerHTML = `<div class="alert alert-error">${escapeHtml(error.message)}</div>`;
    }
  }

  function initUsersPage() {
    const modal = document.getElementById('user-modal');
    document.getElementById('refresh-users').addEventListener('click', loadUsers);
    document.getElementById('modal-close').addEventListener('click', () => modal.close());
    document.getElementById('modal-cancel').addEventListener('click', () => modal.close());

    loadUsers();
  }

  // ── Provider Approval Page ─────────────────────────────────────────────────

  let activeProviderId = null;

  function renderProviderCard(profile) {
    const serviceLabel = profile.service_type === 'airport_pickup' ? 'Driver' : 'Chaperone';
    const approvalStatus = profile.approval_status || 'pending';
    return `
      <article class="shop-card">
        <div class="shop-card-header">
          <div>
            <h3>${escapeHtml(profile.full_name || profile.first_name + ' ' + profile.last_name)}</h3>
            <div class="shop-meta">
              ${escapeHtml(profile.user_email || '')} · ${escapeHtml(serviceLabel)}
              ${profile.city ? ` · ${escapeHtml(profile.city)}` : ''}
            </div>
          </div>
          <span class="status-pill status-${approvalStatus}">${escapeHtml(approvalStatus)}</span>
        </div>
        <div class="shop-meta">
          ${profile.service_type === 'airport_pickup'
            ? `${escapeHtml(profile.vehicle_model || '')} ${escapeHtml(profile.vehicle_year || '')} · ${escapeHtml(profile.license_plate_number || '')}`
            : `SIM: ${escapeHtml(profile.sim_card_reference || '—')} · TFN: ${escapeHtml(profile.tax_file_number_reference || '—')}`
          }
          · registered ${formatDate(profile.registered_at)}
        </div>
        <div class="shop-card-actions">
          <button class="btn btn-secondary" data-action="view-provider" data-id="${profile.id}">View details</button>
          ${approvalStatus === 'pending' ? `
            <button class="btn btn-primary" data-action="approve-provider" data-id="${profile.id}">Approve</button>
            <button class="btn btn-danger" data-action="reject-provider" data-id="${profile.id}">Reject</button>
          ` : ''}
        </div>
      </article>
    `;
  }

  async function loadProviders() {
    const loadingEl = document.getElementById('providers-loading');
    const emptyEl = document.getElementById('providers-empty');
    const listEl = document.getElementById('providers-list');
    const errorEl = document.getElementById('providers-error');
    const serviceFilter = document.getElementById('service-filter');
    const statusFilter = document.getElementById('status-filter');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const serviceType = serviceFilter ? serviceFilter.value : '';
      const approvalStatus = statusFilter ? statusFilter.value : '';
      const params = new URLSearchParams();
      if (serviceType) params.set('service_type', serviceType);
      if (approvalStatus) params.set('status', approvalStatus);
      const qs = params.toString();
      const url = '/api/services/admin/providers/approvals/' + (qs ? `?${qs}` : '');
      const data = await api(url);
      const providers = Array.isArray(data) ? data : (data.results || []);
      loadingEl.classList.add('hidden');

      if (!providers.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = providers.map(renderProviderCard).join('');
      bindProviderActions();
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

  function bindProviderActions() {
    document.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const providerId = button.dataset.id;
        const action = button.dataset.action;

        if (action === 'view-provider') {
          await openProviderModal(providerId);
          return;
        }

        if (action === 'approve-provider') {
          await processProvider(providerId, 'approve');
          return;
        }

        if (action === 'reject-provider') {
          const reason = window.prompt('Rejection reason:');
          if (!reason) return;
          await processProvider(providerId, 'reject', reason);
        }
      });
    });
  }

  async function openProviderModal(providerId) {
    activeProviderId = providerId;
    const modal = document.getElementById('provider-modal');
    const body = document.getElementById('modal-body');
    const notes = document.getElementById('modal-notes');

    notes.value = '';
    body.innerHTML = '<div class="loading">Loading provider details…</div>';
    modal.showModal();

    try {
      const profile = await api(`/api/services/admin/providers/${providerId}/approval-detail/`);
      const serviceLabel = profile.service_type === 'airport_pickup' ? 'Driver' : 'Chaperone';
      document.getElementById('modal-provider-name').textContent =
        `${escapeHtml(profile.full_name || profile.first_name + ' ' + profile.last_name)} — ${serviceLabel}`;
      document.getElementById('modal-provider-meta').textContent =
        `${profile.city || ''}, ${profile.country_code || ''} · Status: ${profile.approval_status || 'pending'}`;

      let detailsHtml = `
        <div class="detail-grid">
          <div class="detail-block"><strong>First name</strong>${escapeHtml(profile.first_name || '—')}</div>
          <div class="detail-block"><strong>Last name</strong>${escapeHtml(profile.last_name || '—')}</div>
          <div class="detail-block"><strong>National ID</strong>${escapeHtml(profile.national_identity_number || '—')}</div>
          <div class="detail-block"><strong>Emergency contact</strong>${escapeHtml(profile.emergency_contact || '—')}</div>
          <div class="detail-block"><strong>Country</strong>${escapeHtml(profile.country_code || '—')}</div>
          <div class="detail-block"><strong>City</strong>${escapeHtml(profile.city || '—')}</div>
        </div>
      `;

      if (profile.service_type === 'airport_pickup') {
        detailsHtml += `
          <h3 style="margin-top:20px; margin-bottom:12px;">License & Vehicle</h3>
          <div class="detail-grid">
            <div class="detail-block"><strong>License #</strong>${escapeHtml(profile.license_number || '—')}</div>
            <div class="detail-block"><strong>License state</strong>${escapeHtml(profile.license_state_country || '—')}</div>
            <div class="detail-block"><strong>License expires</strong>${escapeHtml(profile.license_expiration_date || '—')}</div>
            <div class="detail-block"><strong>Vehicle</strong>${escapeHtml(profile.vehicle_model || '')} ${escapeHtml(profile.vehicle_year || '')}</div>
            <div class="detail-block"><strong>Colour</strong>${escapeHtml(profile.vehicle_colour || '—')}</div>
            <div class="detail-block"><strong>Plate #</strong>${escapeHtml(profile.license_plate_number || '—')}</div>
            <div class="detail-block"><strong>VIN</strong>${escapeHtml(profile.vin || '—')}</div>
          </div>
          ${profile.driver_license_image ? `<div class="detail-block" style="margin-top:12px;"><strong>License image</strong><br><a href="${profile.driver_license_image}" target="_blank" rel="noopener">View license</a></div>` : ''}
        `;
      } else if (profile.service_type === 'chaperone') {
        detailsHtml += `
          <h3 style="margin-top:20px; margin-bottom:12px;">Chaperone Details</h3>
          <div class="detail-grid">
            <div class="detail-block"><strong>SIM reference</strong>${escapeHtml(profile.sim_card_reference || '—')}</div>
            <div class="detail-block"><strong>TFN reference</strong>${escapeHtml(profile.tax_file_number_reference || '—')}</div>
            <div class="detail-block"><strong>Offers translation</strong>${profile.offers_translation_service ? 'Yes' : 'No'}</div>
          </div>
        `;
      }

      if (profile.rejection_reason) {
        detailsHtml += `
          <div class="detail-block" style="margin-top:20px; border-color: rgba(239,68,68,0.35);">
            <strong style="color:#fca5a5;">Rejection reason</strong>
            <p style="margin:0;">${escapeHtml(profile.rejection_reason)}</p>
          </div>
        `;
      }

      if (profile.eligibility) {
        const el = profile.eligibility;
        const pct = el.total ? Math.round((el.passed / el.total) * 100) : 0;
        const barColor = el.eligible ? '#10b981' : '#ef4444';
        const bgColor = el.eligible ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)';
        const borderColor = el.eligible ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)';
        detailsHtml += `
          <h3 style="margin-top:20px; margin-bottom:12px;">Eligibility Checklist</h3>
          <div style="background:${bgColor}; border:1px solid ${borderColor}; border-radius:10px; padding:14px; margin-bottom:12px; display:flex; align-items:center; gap:12px;">
            <div style="flex:1;">
              <strong style="color:${el.eligible ? '#059669' : '#dc2626'}">${el.eligible ? 'Meets all eligibility criteria' : 'Does not meet all criteria'}</strong>
              <div style="font-size:12px; color:#888; margin-top:2px;">${el.passed} of ${el.total} requirements met</div>
            </div>
            <div style="width:100px; height:8px; background:#e5e7eb; border-radius:4px; overflow:hidden;">
              <div style="width:${pct}%; height:100%; background:${barColor}; border-radius:4px;"></div>
            </div>
          </div>
          <div class="detail-grid">
            ${el.checks.map(c => `
              <div class="detail-block" style="display:flex; align-items:flex-start; gap:8px; ${c.passed ? '' : 'background:rgba(239,68,68,0.05); border-color:rgba(239,68,68,0.2);'}">
                <span style="color:${c.passed ? '#10b981' : '#ef4444'}; font-size:14px; margin-top:1px;">${c.passed ? '&#10003;' : '&#10007;'}</span>
                <div>
                  <strong>${escapeHtml(c.label)}</strong>
                  ${c.detail ? `<div style="font-size:11px; color:#888;">${escapeHtml(c.detail)}</div>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        `;
      }

      if (profile.documents && profile.documents.length) {
        const present = profile.documents.filter(d => d.url);
        const missing = profile.documents.filter(d => !d.url);
        detailsHtml += `
          <h3 style="margin-top:20px; margin-bottom:12px;">Uploaded Documents (${present.length})</h3>
          <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:10px; margin-bottom:12px;">
            ${present.map(d => `
              <a href="${d.url}" target="_blank" rel="noopener" style="display:block; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; text-decoration:none; transition:transform 0.15s;">
                <img src="${d.url}" alt="${escapeHtml(d.label)}" style="width:100%; aspect-ratio:4/3; object-fit:cover; display:block;" />
                <div style="padding:4px 8px; font-size:11px; font-weight:600; color:#374151; background:#f9fafb; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(d.label)}</div>
              </a>
            `).join('')}
          </div>
          ${missing.length ? `
            <div style="background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.25); border-radius:8px; padding:10px; margin-bottom:12px;">
              <strong style="font-size:11px; color:#b45309; text-transform:uppercase; letter-spacing:0.05em;">Missing documents</strong>
              <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:6px;">
                ${missing.map(d => `<span style="font-size:11px; padding:2px 8px; border:1px solid rgba(245,158,11,0.3); border-radius:4px; background:#fff; color:#92400e;">&#10007; ${escapeHtml(d.label)}</span>`).join('')}
              </div>
            </div>
          ` : ''}
        `;
      }

      body.innerHTML = detailsHtml;
    } catch (error) {
      body.innerHTML = `<div class="alert alert-error">${escapeHtml(error.message)}</div>`;
    }
  }

  async function processProvider(providerId, action, notes = '') {
    const payload = { action };
    if (notes) payload.notes = notes;

    await api(`/api/services/admin/providers/${providerId}/process-approval/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    const modal = document.getElementById('provider-modal');
    if (modal && modal.open) modal.close();

    await loadProviders();
  }

  function initProvidersPage() {
    const modal = document.getElementById('provider-modal');
    document.getElementById('refresh-providers').addEventListener('click', loadProviders);
    document.getElementById('service-filter').addEventListener('change', loadProviders);
    const statusFilter = document.getElementById('status-filter');
    if (statusFilter) statusFilter.addEventListener('change', loadProviders);
    document.getElementById('modal-close').addEventListener('click', () => modal.close());
    document.getElementById('modal-approve').addEventListener('click', async () => {
      if (!activeProviderId) return;
      const notes = document.getElementById('modal-notes').value.trim();
      await processProvider(activeProviderId, 'approve', notes);
    });
    document.getElementById('modal-reject').addEventListener('click', async () => {
      if (!activeProviderId) return;
      const notes = document.getElementById('modal-notes').value.trim();
      if (!notes) {
        alert('Please enter a rejection reason in the notes field.');
        return;
      }
      await processProvider(activeProviderId, 'reject', notes);
    });

    loadProviders();
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
  }  
  // ── Eligibility Approval Page ─────────────────────────────────────────────

  let activeEligibilityId = null;

  const ELIGIBILITY_STATUS_LABELS = {
    pending: 'Pending',
    processing: 'Processing',
    approved: 'Approved',
    conditionally_approved: 'Conditionally approved',
    rejected: 'Rejected',
  };

  function pathwayLabel(pathway) {
    return pathway === 'b' ? 'Home country' : 'Destination';
  }

  function renderEligibilityCard(item) {
    const status = ELIGIBILITY_STATUS_LABELS[item.status] || item.status || 'pending';
    return `
      <article class="shop-card">
        <div class="shop-card-header">
          <div>
            <h3>${escapeHtml(item.user_name || item.user_email)}</h3>
            <div class="shop-meta">
              ${escapeHtml(item.user_email || '')} · Pathway ${escapeHtml(pathwayLabel(item.pathway))}
              ${item.destination_city ? ` · ${escapeHtml(item.destination_city)}${item.destination_country ? ', ' + escapeHtml(item.destination_country.toUpperCase()) : ''}` : ''}
            </div>
          </div>
          <span class="status-pill status-${item.status || 'pending'}">${escapeHtml(status)}</span>
        </div>
        <div class="shop-meta">
          ${item.documents_count || 0} document(s) uploaded · submitted ${formatDate(item.created_at)}
        </div>
        <div class="shop-card-actions">
          <button class="btn btn-secondary" data-action="view-eligibility" data-id="${item.id}">View details</button>
          ${['pending', 'processing'].includes(item.status) ? `
            <button class="btn btn-primary" data-action="approve-eligibility" data-id="${item.id}">Approve</button>
            <button class="btn btn-danger" data-action="reject-eligibility" data-id="${item.id}">Reject</button>
          ` : ''}
        </div>
      </article>
    `;
  }

  async function loadEligibility() {
    const loadingEl = document.getElementById('eligibility-loading');
    const emptyEl = document.getElementById('eligibility-empty');
    const listEl = document.getElementById('eligibility-list');
    const errorEl = document.getElementById('eligibility-error');
    const pathwayFilter = document.getElementById('pathway-filter');
    const statusFilter = document.getElementById('status-filter');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const pathway = pathwayFilter ? pathwayFilter.value : '';
      const status = statusFilter ? statusFilter.value : '';
      const params = new URLSearchParams();
      if (pathway) params.set('pathway', pathway);
      if (status) params.set('status', status);
      const qs = params.toString();
      const url = '/api/plan/admin/eligibility/' + (qs ? `?${qs}` : '');
      const data = await api(url);
      const items = Array.isArray(data) ? data : (data.results || []);
      loadingEl.classList.add('hidden');

      if (!items.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = items.map(renderEligibilityCard).join('');
      bindEligibilityActions();
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

  function bindEligibilityActions() {
    document.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const id = button.dataset.id;
        const action = button.dataset.action;

        if (action === 'view-eligibility') {
          await openEligibilityModal(id);
          return;
        }

        if (action === 'approve-eligibility') {
          await processEligibility(id, 'approve');
          return;
        }

        if (action === 'reject-eligibility') {
          const reason = window.prompt('Rejection reason:');
          if (!reason) return;
          await processEligibility(id, 'reject', reason);
        }
      });
    });
  }

  async function openEligibilityModal(id) {
    activeEligibilityId = id;
    const modal = document.getElementById('eligibility-modal');
    const body = document.getElementById('modal-body');
    const notes = document.getElementById('modal-notes');

    notes.value = '';
    body.innerHTML = '<div class="loading">Loading eligibility details…</div>';
    modal.showModal();

    try {
      const item = await api(`/api/plan/admin/eligibility/${id}/`);
      document.getElementById('modal-applicant').textContent =
        `${escapeHtml(item.user_name || item.user_email)} — Pathway ${escapeHtml(pathwayLabel(item.pathway))}`;
      document.getElementById('modal-meta').textContent =
        `${item.user_email || item.email || ''} · Status: ${escapeHtml(ELIGIBILITY_STATUS_LABELS[item.status] || item.status || 'pending')}`;

      let detailsHtml = `
        <div class="detail-grid">
          <div class="detail-block"><strong>Full name</strong>${escapeHtml(item.user_name || '—')}</div>
          <div class="detail-block"><strong>Email</strong>${escapeHtml(item.user_email || item.email || '—')}</div>
          <div class="detail-block"><strong>Phone</strong>${escapeHtml(item.phone || '—')}</div>
          <div class="detail-block"><strong>Pathway</strong>${escapeHtml(pathwayLabel(item.pathway))}</div>
          <div class="detail-block"><strong>Destination</strong>${escapeHtml(item.destination_city ? item.destination_city + ', ' + (item.destination_country || '').toUpperCase() : (item.destination_country || '').toUpperCase())}</div>
          <div class="detail-block"><strong>Submitted</strong>${formatDate(item.created_at)}</div>
        </div>
      `;

      const extra = [];
      if (item.visa_expiry) extra.push(['Visa expiry', item.visa_expiry]);
      if (item.passport_expiry) extra.push(['Passport expiry', item.passport_expiry]);
      if (item.migration_doc_type) extra.push(['Migration doc type', item.migration_doc_type]);
      if (item.reviewed_at) extra.push(['Reviewed', formatDate(item.reviewed_at)]);

      if (extra.length) {
        detailsHtml += `
          <h3 style="margin-top:20px; margin-bottom:12px;">Additional details</h3>
          <div class="detail-grid">
            ${extra.map(([label, value]) => `<div class="detail-block"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</div>`).join('')}
          </div>
        `;
      }

      if (item.rejection_reason) {
        detailsHtml += `
          <div class="detail-block" style="margin-top:20px; border-color: rgba(239,68,68,0.35);">
            <strong style="color:#fca5a5;">Rejection reason</strong>
            <p style="margin:0;">${escapeHtml(item.rejection_reason)}</p>
          </div>
        `;
      }

      const documents = item.documents || [];
      detailsHtml += `
        <h3 style="margin-top:20px; margin-bottom:12px;">Uploaded Documents (${documents.length})</h3>
        ${documents.length ? `
          <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:10px; margin-bottom:12px;">
            ${documents.map(d => `
              <a href="${d.file}" target="_blank" rel="noopener" style="display:block; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; text-decoration:none; transition:transform 0.15s;">
                <img src="${d.file}" alt="${escapeHtml(d.document_type_display || d.document_type)}" style="width:100%; aspect-ratio:4/3; object-fit:cover; display:block;" />
                <div style="padding:4px 8px; font-size:11px; font-weight:600; color:#374151; background:#f9fafb; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(d.document_type_display || d.document_type)}</div>
              </a>
            `).join('')}
          </div>
        ` : '<p class="shop-meta">No documents uploaded.</p>'}
      `;

      body.innerHTML = detailsHtml;
    } catch (error) {
      body.innerHTML = `<div class="alert alert-error">${escapeHtml(error.message)}</div>`;
    }
  }

  async function processEligibility(id, action, notes = '') {
    const payload = { action };
    if (notes) payload.notes = notes;

    await api(`/api/plan/admin/eligibility/${id}/process/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    const modal = document.getElementById('eligibility-modal');
    if (modal && modal.open) modal.close();

    await loadEligibility();
  }

  function initEligibilityPage() {
    const modal = document.getElementById('eligibility-modal');
    document.getElementById('refresh-eligibility').addEventListener('click', loadEligibility);
    document.getElementById('pathway-filter').addEventListener('change', loadEligibility);
    const statusFilter = document.getElementById('status-filter');
    if (statusFilter) statusFilter.addEventListener('change', loadEligibility);
    document.getElementById('modal-close').addEventListener('click', () => modal.close());
    document.getElementById('modal-approve').addEventListener('click', async () => {
      if (!activeEligibilityId) return;
      const notes = document.getElementById('modal-notes').value.trim();
      await processEligibility(activeEligibilityId, 'approve', notes);
    });
    document.getElementById('modal-reject').addEventListener('click', async () => {
      if (!activeEligibilityId) return;
      const notes = document.getElementById('modal-notes').value.trim();
      if (!notes) {
        alert('Please enter a rejection reason in the notes field.');
        return;
      }
      await processEligibility(activeEligibilityId, 'reject', notes);
    });

    loadEligibility();
  }

  async function initEligibilityStats() {
    try {
      const stats = await api('/api/plan/admin/eligibility/stats/');
      document.getElementById('elig-stat-total').textContent = stats.total;
      document.getElementById('elig-stat-pending').textContent = stats.pending + stats.processing;
      document.getElementById('elig-stat-approved').textContent = stats.approved;
      document.getElementById('elig-stat-conditional').textContent = stats.conditionally_approved;
      document.getElementById('elig-stat-rejected').textContent = stats.rejected;
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
      }
    }
  }

  // ── Community members (super admin portal) ───────────────────────────────

  async function loadCommunityMembers() {
    const loadingEl = document.getElementById('communities-loading');
    const emptyEl = document.getElementById('communities-empty');
    const listEl = document.getElementById('communities-list');
    const errorEl = document.getElementById('communities-error');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const data = await api('/api/community/admin/memberships/');
      const members = Array.isArray(data) ? data : (data.results || []);
      const q = (document.getElementById('community-search')?.value || '').trim().toLowerCase();
      const filtered = q
        ? members.filter((m) =>
            (m.username || '').toLowerCase().includes(q) ||
            (m.email || '').toLowerCase().includes(q) ||
            (m.community_name || '').toLowerCase().includes(q)
          )
        : members;

      loadingEl.classList.add('hidden');

      document.getElementById('community-stat-total').textContent = members.length;
      const groups = new Set(members.map((m) => m.community_id));
      document.getElementById('community-stat-groups').textContent = groups.size;
      const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
      document.getElementById('community-stat-24h').textContent =
        members.filter((m) => m.approved_at && new Date(m.approved_at).getTime() >= dayAgo).length;

      if (!filtered.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = filtered.map(renderCommunityMemberCard).join('');
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

  function renderCommunityMemberCard(m) {
    const roleLabel = m.role === 'admin' ? 'Admin' : m.role === 'moderator' ? 'Moderator' : 'Member';
    const emailHtml = m.email ? ` <span class="shop-meta">(${escapeHtml(m.email)})</span>` : '';
    return `
      <article class="shop-card">
        <div class="shop-card-header">
          <div>
            <h3>${escapeHtml(m.username || 'Unknown member')}${emailHtml}</h3>
            <div class="shop-meta">
              Group: <strong>${escapeHtml(m.community_name || '—')}</strong> · ${escapeHtml(roleLabel)}
            </div>
          </div>
          <span class="status-pill status-approved">Accepted</span>
        </div>
        <div class="shop-meta" style="display:grid; gap:4px;">
          <div>Requested: <strong>${m.requested_at ? formatDate(m.requested_at) : '—'}</strong></div>
          <div style="color:#d97706;">Accepted into group: <strong>${m.approved_at ? formatDate(m.approved_at) : formatDate(m.requested_at)}</strong></div>
        </div>
      </article>
    `;
  }

  async function initDashboardCommunitySection() {
    const listEl = document.getElementById('community-recent-list');
    const errorEl = document.getElementById('community-recent-error');
    if (!listEl) return;

    try {
      const data = await api('/api/community/admin/memberships/');
      const members = (Array.isArray(data) ? data : (data.results || [])).slice(0, 8);
      document.getElementById('community-recent-total').textContent = members.length;
      if (!members.length) {
        listEl.innerHTML = '<div class="loading" style="padding:16px;">No members accepted into groups yet.</div>';
        return;
      }
      listEl.innerHTML = members.map(renderCommunityMemberCard).join('');
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
        return;
      }
      showError(errorEl, error.message);
    }
  }

  function initCommunityMembersPage() {
    document.getElementById('refresh-communities').addEventListener('click', loadCommunityMembers);
    document.getElementById('community-search').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loadCommunityMembers();
    });
    loadCommunityMembers();
  }

  function formatDate(value) {
    if (!value) return 'recently';
    return new Date(value).toLocaleString();
  }

  function formatShortTime(value) {
    if (!value) return '';
    const d = new Date(value);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function formatBubbleTime(value) {
    if (!value) return '';
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function initialsOf(name) {
    const parts = String(name || '?')
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    const letters = parts.length > 1
      ? (parts[0][0] || '') + (parts[parts.length - 1][0] || '')
      : (name.charAt(0) || '?');
    return letters.toUpperCase();
  }

  const CHECK_READ_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">' +
    '<path d="M9.5 16.2 4.8 11.5 3.4 12.9 9.5 19 20.6 7.9l-1.4-1.4z"/></svg>';
  const CHECK_SENT_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">' +
    '<path d="M9.5 16.2 4.8 11.5 3.4 12.9 9.5 19 20.6 7.9l-1.4-1.4z" opacity="0.55"/></svg>';

  // ── Support inbox ───────────────────────────────────────────────────────────

  let supportConversations = [];
  let activeConversationId = null;
  let adminsSocket = null;
  let chatSocket = null;
  let lastSupportSearch = '';

  function wsBase() {
    const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    return `${proto}${window.location.host}`;
  }

  function renderSupportRow(conv) {
    const customer = conv.customer || {};
    const last = conv.last_message || {};
    const name = customer.full_name || customer.email || 'Unknown customer';
    const unread = conv.unread_count || 0;
    const active = conv.id === activeConversationId;
    const isCustomerSender =
      Boolean(customer.id) && Number(last.sender_id) === Number(customer.id);
    const preview = escapeHtml(last.body || 'No messages yet');
    const senderHint = last.body && !isCustomerSender ? 'You: ' : '';
    const time = formatShortTime(last.created_at || conv.updated_at);
    return `
      <button type="button" data-support-id="${conv.id}" class="support-row${active ? ' active' : ''}">
        <span class="support-avatar">${escapeHtml(initialsOf(name))}</span>
        <span class="support-row-body">
          <span class="support-row-top">
            <span class="support-row-name">${escapeHtml(name)}</span>
            ${time ? `<span class="support-row-time">${escapeHtml(time)}</span>` : ''}
          </span>
          ${conv.subject ? `<span class="support-row-subject">${escapeHtml(conv.subject)}</span>` : ''}
          <span class="support-row-preview">
            ${unread > 0 ? CHECK_READ_SVG : ''}
            ${escapeHtml(senderHint)}${preview}
          </span>
        </span>
        ${unread > 0 ? `<span class="support-unread">${unread}</span>` : ''}
      </button>
    `;
  }

  async function loadSupportInbox() {
    const loadingEl = document.getElementById('support-loading');
    const emptyEl = document.getElementById('support-empty');
    const listEl = document.getElementById('support-list');
    const errorEl = document.getElementById('support-error');

    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    listEl.innerHTML = '';
    errorEl.classList.add('hidden');

    try {
      const q = document.getElementById('support-search').value.trim();
      lastSupportSearch = q;
      const data = await api('/api/messaging/support/inbox/' + (q ? `?q=${encodeURIComponent(q)}` : ''));
      supportConversations = Array.isArray(data) ? data : (data.results || []);

      document.getElementById('support-stat-open').textContent = supportConversations.length;
      document.getElementById('support-stat-unread').textContent =
        supportConversations.filter((c) => (c.unread_count || 0) > 0).length;
      document.getElementById('support-stat-unresolved').textContent = supportConversations.length;
      const countEl = document.getElementById('support-pane-count');
      if (countEl) {
        countEl.textContent = `${supportConversations.length} ${supportConversations.length === 1 ? 'thread' : 'threads'}`;
      }

      loadingEl.classList.add('hidden');
      if (!supportConversations.length) {
        emptyEl.classList.remove('hidden');
        return;
      }

      listEl.innerHTML = supportConversations.map(renderSupportRow).join('');
      listEl.querySelectorAll('[data-support-id]').forEach((row) => {
        row.addEventListener('click', () => {
          const conv = supportConversations.find((c) => c.id === Number(row.dataset.supportId));
          if (conv) openSupportConversation(conv.id, conv);
        });
      });
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

  function openSupportConversation(id, conv) {
    activeConversationId = id;
    document.querySelectorAll('[data-support-id]').forEach((row) => {
      row.classList.toggle('active', Number(row.dataset.supportId) === id);
    });

    const customer = conv.customer || {};
    const name = customer.full_name || customer.email || 'Customer';
    document.getElementById('chat-title').textContent = name;
    document.getElementById('chat-sub').textContent =
      `${customer.email || ''}${conv.subject ? ` · ${conv.subject}` : ''}`.trim();
    const avatarEl = document.getElementById('chat-avatar');
    if (avatarEl) avatarEl.textContent = initialsOf(name);

    setSupportChatStatus(false, 'Connecting…');

    document.getElementById('chat-empty').classList.add('hidden');
    document.getElementById('chat-messages').classList.remove('hidden');
    document.getElementById('chat-compose').classList.remove('hidden');

    loadSupportMessages(id);
    connectSupportChat(id);
    // Refresh the inbox so the row's unread badge clears for this thread.
    loadSupportInbox();
  }

  function setSupportChatStatus(online, label) {
    const dot = document.getElementById('chat-dot');
    const text = document.getElementById('chat-status-text');
    if (dot) dot.classList.toggle('online', Boolean(online));
    if (text) text.textContent = label || (online ? 'Online' : 'Offline');
  }

  async function loadSupportMessages(id) {
    const container = document.getElementById('chat-messages');
    container.innerHTML = '<div class="loading">Loading messages…</div>';
    try {
      const data = await api(`/api/messaging/conversations/${id}/messages/`);
      const messages = Array.isArray(data) ? data : (data.results || []);
      container.innerHTML = '';
      if (!messages.length) {
        container.classList.add('empty');
        container.innerHTML =
          '<div class="support-empty-chat"><strong>No messages yet</strong><br />This support thread just opened. Ask how you can help.</div>';
      } else {
        container.classList.remove('empty');
        messages.forEach((msg) => appendMessageBubble(msg, false));
      }
      container.scrollTop = container.scrollHeight;
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        clearSession();
        window.location.href = '/portal/login/';
        return;
      }
      container.innerHTML = '<div style="color:#dc2626;padding:20px;text-align:center;">Could not load messages.</div>';
    }
  }

  function adminUserId() {
    const user = getUser();
    return user ? user.id : null;
  }

  function appendMessageBubble(msg, optimistic) {
    const container = document.getElementById('chat-messages');
    container.classList.remove('empty');
    const isMine = Number(msg.sender && msg.sender.id) === Number(adminUserId());
    const senderName = (msg.sender && msg.sender.full_name) || 'Customer';
    const isRead = Boolean(msg.is_read);

    // Consecutive messages from the same sender are grouped (WhatsApp-style)
    const prev = container.lastElementChild;
    const grouped = !!(prev && prev.dataset.sender === String(msg.sender && msg.sender.id));

    const row = document.createElement('div');
    row.className = 'support-bubble-row ' + (isMine ? 'mine' : 'theirs');
    row.dataset.sender = String(msg.sender && msg.sender.id);

    if (!isMine) {
      const side = document.createElement('div');
      side.className = 'support-bubble-side' + (grouped ? '' : ' avatar');
      if (!grouped) side.textContent = initialsOf(senderName);
      row.appendChild(side);
    }

    const bubble = document.createElement('div');
    bubble.className = 'support-bubble';
    if (!grouped) bubble.classList.add('support-bubble-tail');

    if (msg.reply_to && msg.reply_to.body) {
      const quote = document.createElement('div');
      quote.className = 'support-bubble-quote';
      const quoteName = document.createElement('span');
      quoteName.className = 'support-bubble-quote-name';
      quoteName.textContent = (msg.reply_to.sender && msg.reply_to.sender.full_name) || 'Message';
      const quoteBody = document.createElement('span');
      quoteBody.textContent = msg.reply_to.body;
      quote.appendChild(quoteName);
      quote.appendChild(quoteBody);
      bubble.appendChild(quote);
    }

    if (msg.body) {
      const body = document.createElement('div');
      body.textContent = msg.body;
      bubble.appendChild(body);
    }

    const attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
    attachments.forEach((att) => {
      const a = document.createElement('a');
      a.className = 'support-bubble-attach';
      a.href = att.url || '#';
      a.target = '_blank';
      a.rel = 'noreferrer';
      const size = formatBytes(att.filesize);
      a.textContent = `📎 ${att.filename || 'Attachment'}${size ? ` (${size})` : ''}`;
      bubble.appendChild(a);
    });

    const meta = document.createElement('div');
    meta.className = 'support-bubble-meta';
    const timeEl = document.createElement('span');
    timeEl.className = 'support-bubble-time';
    timeEl.textContent = formatBubbleTime(msg.created_at);
    meta.appendChild(timeEl);
    if (isMine) {
      const checks = document.createElement('span');
      checks.className = 'support-bubble-checks' + (isRead ? ' is-read' : '');
      checks.innerHTML = isRead ? CHECK_READ_SVG : CHECK_SENT_SVG;
      meta.appendChild(checks);
    }
    bubble.appendChild(meta);

    row.appendChild(bubble);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
  }

  function connectSupportChat(id) {
    if (chatSocket) {
      chatSocket.onclose = null;
      chatSocket.close();
      chatSocket = null;
    }
    const token = getToken();
    if (!token) return;
    chatSocket = new WebSocket(`${wsBase()}/ws/messaging/${id}/?token=${token}`);
    chatSocket.onopen = () => setSupportChatStatus(true, 'Online');
    chatSocket.onmessage = (event) => {
      let data = {};
      try { data = JSON.parse(event.data); } catch (e) { return; }
      if (data.type === 'chat_message') {
        appendMessageBubble(data.message, false);
        loadSupportInbox();
      }
    };
    chatSocket.onclose = () => {
      chatSocket = null;
      setSupportChatStatus(false, 'Offline');
    };
  }

  function sendSupportReply() {
    const input = document.getElementById('reply-input');
    const sendBtn = document.getElementById('reply-send');
    const body = input.value.trim();
    if (!body || !chatSocket || !activeConversationId) return;
    if (chatSocket.readyState !== WebSocket.OPEN) {
      alert('Chat is not connected. Please wait a moment and try again.');
      return;
    }
    chatSocket.send(JSON.stringify({ type: 'chat_message', body }));
    input.value = '';
    input.focus();
    if (sendBtn) sendBtn.disabled = true;
    // The live chat_message echo (or the support_update refresh) re-enables it.
    setTimeout(() => { if (sendBtn) sendBtn.disabled = false; }, 600);
  }

  function connectAdminsSocket() {
    const token = getToken();
    if (!token) return;
    try {
      adminsSocket = new WebSocket(`${wsBase()}/ws/support/admins/?token=${token}`);
      adminsSocket.onmessage = (event) => {
        let data = {};
        try { data = JSON.parse(event.data); } catch (e) { return; }
        if (data.type === 'support_update') {
          loadSupportInbox();
          if (activeConversationId && Number(data.conversation_id) === Number(activeConversationId)) {
            loadSupportMessages(activeConversationId);
          }
        }
      };
      adminsSocket.onclose = () => {
        adminsSocket = null;
      };
    } catch (e) {
      // Live updates are best-effort; the Refresh button always works.
      adminsSocket = null;
    }
  }

  function initSupportPage() {
    document.getElementById('refresh-support').addEventListener('click', loadSupportInbox);
    document.getElementById('support-search').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loadSupportInbox();
    });
    document.getElementById('reply-send').addEventListener('click', sendSupportReply);
    document.getElementById('reply-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendSupportReply();
      }
    });
    connectAdminsSocket();
    loadSupportInbox();
  }

  return {
    requireAuth,
    initShell,
    initLoginPage,
    initRegisterPage,
    initDashboardPage,
    initDashboardProviderStats,
    initShopItemsPage,
    initProvidersPage,
    initUsersPage,
    initEligibilityPage,
    initEligibilityStats,
    initDashboardCommunitySection,
    initCommunityMembersPage,
    initSupportPage,
  };
})();
