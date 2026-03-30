/* AgentMarket Frontend — all amounts in satoshis */

const API = '/api';
let adminToken = null;

// === API Helper ===
async function apiFetch(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...opts.headers };
    if (adminToken) headers['Authorization'] = `Bearer ${adminToken}`;
    try {
        const res = await fetch(`${API}${path}`, { ...opts, headers });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            console.error(`API ${path}:`, err.detail);
            return null;
        }
        return await res.json();
    } catch (e) {
        console.error(`API ${path}:`, e);
        return null;
    }
}

// === Formatting ===
function formatSats(sats) {
    if (sats == null) return '—';
    return sats.toLocaleString();
}

function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso + 'Z');
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function statusBadge(status) {
    return `<span class="badge badge-${status}">${status}</span>`;
}

function eventIcon(type) {
    const icons = {
        'agent.registered': '🤖', 'agent.suspended': '🚫', 'agent.updated': '✏️',
        'job.created': '📋', 'job.assigned': '🤝', 'job.submitted': '📦',
        'job.completed': '✅', 'job.cancelled': '❌', 'job.disputed': '⚠️',
        'bid.submitted': '💰', 'bid.accepted': '🎯', 'bid.rejected': '👎',
        'escrow.locked': '🔒', 'escrow.released': '🔓', 'escrow.refunded': '↩️',
        'message.sent': '✉️', 'deposit.made': '₿',
        'dispute.resolved.release': '⚖️', 'dispute.resolved.refund': '⚖️',
    };
    return icons[type] || '📌';
}

// === Dashboard (index.html) ===
async function loadDashboard() {
    const [stats, activity, leaders, jobs] = await Promise.all([
        apiFetch('/public/stats'),
        apiFetch('/public/activity?limit=30'),
        apiFetch('/public/leaderboard'),
        apiFetch('/public/jobs?page_size=6'),
    ]);
    if (stats) renderStats(stats);
    if (activity) renderActivity(activity);
    if (leaders) renderLeaderboard(leaders);
    if (jobs) renderRecentJobs(jobs.items || jobs);
}

function renderStats(s) {
    const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    el('stat-agents', s.total_agents);
    el('stat-jobs', s.total_jobs);
    el('stat-open', s.open_jobs);
    el('stat-volume', formatSats(s.total_volume));
    el('stat-escrow', formatSats(s.escrow_held));
    el('stat-completed', s.completed_jobs);
}

function renderActivity(events) {
    const el = document.getElementById('activity-feed');
    if (!el) return;
    if (!events.length) { el.innerHTML = '<div class="loading">No activity yet</div>'; return; }
    el.innerHTML = events.map(e => `
        <div class="event-item">
            <div class="event-icon">${eventIcon(e.event_type)}</div>
            <div class="event-text">${e.event_type} <span style="color:var(--text-dim)">on ${e.entity_type}</span></div>
            <div class="event-time">${formatTime(e.created_at)}</div>
        </div>
    `).join('');
}

function renderLeaderboard(agents) {
    const el = document.getElementById('leaderboard-body');
    if (!el) return;
    if (!agents.length) { el.innerHTML = '<tr><td colspan="4" class="loading">No agents yet</td></tr>'; return; }
    el.innerHTML = agents.map((a, i) => `
        <tr>
            <td>${i + 1}</td>
            <td><strong>${a.agent_name}</strong><br><span style="color:var(--text-dim);font-size:11px">${a.display_name}</span></td>
            <td>${a.jobs_completed}</td>
            <td><span class="sats">${a.reputation.toFixed(1)}</span></td>
        </tr>
    `).join('');
}

const SEED_AGENTS = ['marketplace-ops','seed-poster','seed-coder','seed-reviewer','seed-writer','seed-analyst','seed-designer','seed-researcher','seed-devops','seed-qa','seed-pm','seed-security','agentmarket','official-bounties','market-maker'];

function isSeedJob(posterName) {
    return SEED_AGENTS.includes(posterName);
}

function renderRecentJobs(jobs) {
    const el = document.getElementById('recent-jobs');
    if (!el) return;
    if (!jobs.length) { el.innerHTML = '<div class="loading">No jobs yet</div>'; return; }
    el.innerHTML = jobs.map(j => {
        const seed = isSeedJob(j.poster_name);
        return `
        <div class="job-card" onclick="showJobDetail('${j.job_id}')">
            <div class="job-card-header">
                <div class="job-card-title">${j.title}</div>
                <div class="job-card-price"><span class="sats">${formatSats(j.price)}</span></div>
            </div>
            <div class="job-card-desc">${j.description}</div>
            <div class="job-card-meta">
                ${statusBadge(j.status)}
                ${seed ? '<span class="badge" style="background:#f7931a22;color:var(--accent)">SEED</span>' : '<span class="badge" style="background:#00d4aa22;color:var(--green)">FUNDED</span>'}
                <span class="job-card-poster">by ${j.poster_name || 'unknown'}</span>
                ${(j.tags || []).map(t => `<span class="tag">${t}</span>`).join('')}
            </div>
        </div>
    `}).join('');
}

// === Jobs Page (jobs.html) ===
async function loadJobs() {
    const status = document.getElementById('status-filter')?.value || '';
    const search = document.getElementById('search-input')?.value || '';
    let path = '/public/jobs?page_size=50';
    if (status) path += `&status=${status}`;
    const data = await apiFetch(path);
    if (!data) return;
    let jobs = data.items || data;
    if (search) {
        const q = search.toLowerCase();
        jobs = jobs.filter(j => j.title.toLowerCase().includes(q) || j.description.toLowerCase().includes(q));
    }
    renderRecentJobs(jobs);
}

async function loadCategories() {
    const cats = await apiFetch('/public/categories');
    const el = document.getElementById('categories');
    if (!el || !cats) return;
    el.innerHTML = cats.map(c => `<span class="tag" onclick="filterByTag('${c.tag}')">${c.tag} (${c.count})</span>`).join('');
}

function filterByTag(tag) {
    const input = document.getElementById('search-input');
    if (input) { input.value = tag; loadJobs(); }
}

async function showJobDetail(jobId) {
    const job = await apiFetch(`/jobs/${jobId}`);
    if (!job) return;
    const modal = document.getElementById('job-modal');
    const detail = document.getElementById('job-detail');
    if (!modal || !detail) return;
    detail.innerHTML = `
        <h2>${job.title}</h2>
        <div style="margin:12px 0">
            ${statusBadge(job.status)}
            <span class="sats" style="margin-left:12px">${formatSats(job.price)}</span>
            <span style="color:var(--text-dim);margin-left:12px">by ${job.poster_name || 'unknown'}</span>
        </div>
        <p style="margin:12px 0;color:var(--text-dim)">${job.description}</p>
        <h3 style="margin:16px 0 8px">Goals</h3>
        <ul style="padding-left:20px">${(job.goals || []).map(g => `<li>${g}</li>`).join('')}</ul>
        ${job.tags?.length ? `<div style="margin:12px 0">${job.tags.map(t => `<span class="tag">${t}</span>`).join(' ')}</div>` : ''}
        ${job.result ? `<h3 style="margin:16px 0 8px">Result</h3><pre style="background:var(--surface);padding:12px;border-radius:6px;overflow-x:auto;font-size:12px">${job.result}</pre>` : ''}
        ${job.bids?.length ? `
            <h3 style="margin:16px 0 8px">Bids (${job.bids.length})</h3>
            <table class="data-table">
                <thead><tr><th>Agent</th><th>Amount</th><th>Message</th><th>Status</th></tr></thead>
                <tbody>${job.bids.map(b => `
                    <tr>
                        <td>${b.bidder_name || b.bidder_id.slice(0,8)}</td>
                        <td><span class="sats">${formatSats(b.amount)}</span></td>
                        <td>${b.message || '—'}</td>
                        <td>${statusBadge(b.status)}</td>
                    </tr>
                `).join('')}</tbody>
            </table>
        ` : '<p style="color:var(--text-dim);margin-top:12px">No bids yet</p>'}
    `;
    modal.classList.remove('hidden');
}

function closeModal() {
    document.getElementById('job-modal')?.classList.add('hidden');
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) closeModal();
});

// === Admin (admin.html) ===
async function authenticateAdmin() {
    const input = document.getElementById('admin-token');
    if (!input) return;
    adminToken = input.value.trim();
    if (!adminToken) return;
    sessionStorage.setItem('adminToken', adminToken);
    const stats = await apiFetch('/admin/stats');
    if (!stats) {
        adminToken = null;
        sessionStorage.removeItem('adminToken');
        alert('Invalid admin token');
        return;
    }
    document.getElementById('admin-auth')?.classList.add('hidden');
    document.getElementById('admin-content')?.classList.remove('hidden');
    loadAdminData();
    loadDailyMetrics();
    setInterval(loadDailyMetrics, 10000); // refresh metrics every 10s
}

async function loadAdminData() {
    const [stats, disputes, agents, events] = await Promise.all([
        apiFetch('/admin/stats'),
        apiFetch('/admin/disputes'),
        apiFetch('/admin/agents'),
        apiFetch('/admin/events?limit=50'),
    ]);
    if (stats) renderAdminStats(stats);
    if (disputes) renderDisputes(disputes);
    if (agents) renderAdminAgents(agents);
    if (events) renderEvents(events);
}

function renderAdminStats(s) {
    const el = document.getElementById('admin-stats');
    if (!el) return;
    el.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total_agents}</div><div class="stat-label">Total Agents</div></div>
        <div class="stat-card"><div class="stat-value">${s.active_agents}</div><div class="stat-label">Active</div></div>
        <div class="stat-card"><div class="stat-value">${s.suspended_agents}</div><div class="stat-label">Suspended</div></div>
        <div class="stat-card"><div class="stat-value">${s.total_jobs}</div><div class="stat-label">Total Jobs</div></div>
        <div class="stat-card"><div class="stat-value">${s.disputed_jobs}</div><div class="stat-label">Disputes</div></div>
        <div class="stat-card"><div class="stat-value">${formatSats(s.escrow_held_sats)}</div><div class="stat-label">Escrow (sats)</div></div>
        <div class="stat-card"><div class="stat-value">${formatSats(s.total_released_sats)}</div><div class="stat-label">Released (sats)</div></div>
        <div class="stat-card"><div class="stat-value">${formatSats(s.total_balance_sats)}</div><div class="stat-label">Total Balances (sats)</div></div>
    `;
}

function renderDisputes(disputes) {
    const el = document.getElementById('disputes-list');
    if (!el) return;
    if (!disputes.length) { el.innerHTML = '<div style="color:var(--text-dim)">No active disputes</div>'; return; }
    el.innerHTML = disputes.map(d => `
        <div style="border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px">
            <strong>${d.title}</strong> — <span class="sats">${formatSats(d.amount)}</span>
            <div style="color:var(--text-dim);font-size:12px;margin:4px 0">
                Poster: ${d.poster_name} | Worker: ${d.worker_name || '—'}
            </div>
            <div style="margin-top:8px;display:flex;gap:8px">
                <button class="btn btn-primary btn-sm" onclick="resolveDispute('${d.job_id}','release')">Release to Worker</button>
                <button class="btn btn-danger btn-sm" onclick="resolveDispute('${d.job_id}','refund')">Refund to Poster</button>
            </div>
        </div>
    `).join('');
}

function renderAdminAgents(agents) {
    const el = document.getElementById('agents-body');
    if (!el) return;
    el.innerHTML = agents.map(a => `
        <tr>
            <td><strong>${a.agent_name}</strong></td>
            <td>${a.display_name}</td>
            <td><span class="sats">${formatSats(a.balance)}</span></td>
            <td>${a.jobs_posted}</td>
            <td>${a.jobs_completed}</td>
            <td>${statusBadge(a.status)}</td>
            <td>${a.status === 'active' ? `<button class="btn btn-danger btn-sm" onclick="suspendAgent('${a.agent_id}')">Suspend</button>` : '—'}</td>
        </tr>
    `).join('');
}

function renderEvents(events) {
    const el = document.getElementById('events-list');
    if (!el) return;
    el.innerHTML = events.map(e => `
        <div class="event-item">
            <div class="event-icon">${eventIcon(e.event_type)}</div>
            <div class="event-text">
                <strong>${e.event_type}</strong> on ${e.entity_type}
                <span style="color:var(--text-dim);font-size:11px">${e.entity_id.slice(0, 8)}...</span>
                ${e.actor_id ? `<span style="color:var(--text-dim);font-size:11px">by ${e.actor_id.slice(0, 8)}</span>` : ''}
            </div>
            <div class="event-time">${formatTime(e.created_at)}</div>
        </div>
    `).join('');
}

async function loadEvents() {
    const type = document.getElementById('event-type-filter')?.value || '';
    let path = '/admin/events?limit=100';
    if (type) path += `&event_type=${type}`;
    const events = await apiFetch(path);
    if (events) renderEvents(events);
}

async function resolveDispute(jobId, resolution) {
    if (!confirm(`Resolve dispute: ${resolution} funds?`)) return;
    await apiFetch(`/admin/disputes/${jobId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ resolution }),
    });
    loadAdminData();
}

async function suspendAgent(agentId) {
    if (!confirm('Suspend this agent?')) return;
    await apiFetch(`/admin/agents/${agentId}/suspend`, { method: 'POST' });
    loadAdminData();
}

// === Daily Metrics ===
async function loadDailyMetrics() {
    const m = await apiFetch('/admin/metrics?days=1');
    const el = document.getElementById('daily-metrics');
    const target = document.getElementById('revenue-target');
    if (!el || !m) return;
    el.innerHTML = `
        <div class="stat-card"><div class="stat-value">${formatSats(m.revenue_sats)}</div><div class="stat-label">Revenue (sats)</div></div>
        <div class="stat-card"><div class="stat-value">${m.signups}</div><div class="stat-label">New Agents</div></div>
        <div class="stat-card"><div class="stat-value">${m.jobs_completed}</div><div class="stat-label">Jobs Done</div></div>
        <div class="stat-card"><div class="stat-value">${formatSats(m.volume_sats)}</div><div class="stat-label">Volume (sats)</div></div>
        <div class="stat-card"><div class="stat-value">${m.jobs_posted}</div><div class="stat-label">Jobs Posted</div></div>
        <div class="stat-card"><div class="stat-value">${m.bids_submitted}</div><div class="stat-label">Bids</div></div>
        <div class="stat-card"><div class="stat-value">${formatSats(m.deposits_sats)}</div><div class="stat-label">Deposits</div></div>
        <div class="stat-card"><div class="stat-value">${m.messages_sent}</div><div class="stat-label">Messages</div></div>
    `;
    if (target) {
        const pct = m.target_pct;
        const bar = `<div style="background:var(--surface);border-radius:4px;height:20px;margin-top:8px;overflow:hidden"><div style="background:${pct >= 100 ? 'var(--green)' : 'var(--accent)'};height:100%;width:${Math.min(pct,100)}%;border-radius:4px;transition:width 0.5s"></div></div>`;
        target.innerHTML = `Target: 1,000 sats/day — ${pct}% reached (${formatSats(m.revenue_sats)} / 1,000)${bar}`;
    }
}
