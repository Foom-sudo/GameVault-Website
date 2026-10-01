/* ============================================================
   GameVault V2 — app.js (Vanilla JS, modular IIFE)
   Reads games.json, no hardcoded game data in HTML.
   ============================================================ */
(function () {
  'use strict';

  /* ---------------- constants & state ---------------- */
  var FAV_KEY = 'gamevault-favorites-v2';
  var FEATURED_IDS = ['game-001', 'game-002', 'game-011', 'game-012']; // hand-picked headliners

  var state = {
    games: [],
    query: '',
    filters: { platform: 'all', genre: 'all', status: 'all', year: 'all' },
    sort: 'latest',
    favorites: new Set(),
    currentView: 'home'
  };

  var $ = function (id) { return document.getElementById(id); };
  var HEART = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>';

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* ---------------- Favorites (localStorage) ---------------- */
  var Fav = {
    load: function () {
      try {
        var raw = localStorage.getItem(FAV_KEY);
        var arr = raw ? JSON.parse(raw) : [];
        if (Array.isArray(arr)) arr.forEach(function (id) { state.favorites.add(id); });
      } catch (e) { state.favorites.clear(); }
    },
    save: function () {
      try { localStorage.setItem(FAV_KEY, JSON.stringify(Array.from(state.favorites))); }
      catch (e) { /* storage full / private mode — ignore */ }
    },
    has: function (id) { return state.favorites.has(id); },
    toggle: function (id) {
      if (state.favorites.has(id)) state.favorites.delete(id);
      else state.favorites.add(id);
      Fav.save();
      Fav.updateBadge();
    },
    count: function () { return state.favorites.size; },
    updateBadge: function () {
      var b = $('favBadge');
      if (!b) return;
      var n = Fav.count();
      b.textContent = n;
      b.setAttribute('data-zero', n === 0 ? 'true' : 'false');
      // refresh fav button states on currently rendered cards
      document.querySelectorAll('.fav-btn').forEach(function (btn) {
        var card = btn.closest('.game-card');
        var id = card ? card.dataset.id : (btn.dataset.gameId || '');
        if (id) btn.classList.toggle('active', Fav.has(id));
      });
      var df = $('detailFavBtn');
      if (df && df.dataset.gameId) df.classList.toggle('active', Fav.has(df.dataset.gameId));
    }
  };

  /* ---------------- Data loading ---------------- */
  function loadGames() {
    return fetch('games.json', { cache: 'no-cache' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!Array.isArray(data)) throw new Error('games.json 格式错误');
        state.games = data;
      });
  }

  function showError(msg) {
    var ls = $('loadingScreen'), es = $('errorScreen'), em = $('errorMsg');
    if (ls) ls.classList.add('hidden');
    if (es) es.classList.remove('hidden');
    if (em && msg) em.textContent = msg;
  }

  /* ---------------- derived data ---------------- */
  function allPlatforms() {
    var s = new Set();
    state.games.forEach(function (g) { (g.platforms || []).forEach(function (p) { s.add(p); }); });
    return Array.from(s).sort();
  }
  function allGenres() {
    var s = new Set();
    state.games.forEach(function (g) { (g.genres || []).forEach(function (t) { s.add(t); }); });
    return Array.from(s).sort(function (a, b) { return a.localeCompare(b, 'zh'); });
  }
  function allYears() {
    var s = new Set();
    state.games.forEach(function (g) { if (g.releaseDate) s.add(g.releaseDate.slice(0, 4)); });
    return Array.from(s).sort().reverse();
  }
  function gameById(id) {
    for (var i = 0; i < state.games.length; i++) if (state.games[i].id === id) return state.games[i];
    return null;
  }

  /* ---------------- search / filter / sort ---------------- */
  function matchesQuery(g, q) {
    if (!q) return true;
    q = q.toLowerCase();
    var hay = [g.title, g.developer, g.publisher]
      .concat(g.genres || [], g.tags || [])
      .filter(Boolean).join(' ').toLowerCase();
    return hay.indexOf(q) !== -1;
  }

  function getFiltered() {
    var q = state.query.trim();
    var f = state.filters;
    var list = state.games.filter(function (g) {
      if (!matchesQuery(g, q)) return false;
      if (f.platform !== 'all' && (g.platforms || []).indexOf(f.platform) === -1) return false;
      if (f.genre !== 'all' && (g.genres || []).indexOf(f.genre) === -1) return false;
      if (f.status !== 'all' && g.status !== f.status) return false;
      if (f.year !== 'all' && (!g.releaseDate || g.releaseDate.slice(0, 4) !== f.year)) return false;
      return true;
    });
    return sortGames(list, state.sort);
  }

  function sortGames(list, mode) {
    var arr = list.slice();
    var byDateAsc = function (a, b) { return (a.releaseDate || '').localeCompare(b.releaseDate || ''); };
    if (mode === 'upcoming') arr.sort(byDateAsc);
    else if (mode === 'latest') arr.sort(function (a, b) { return byDateAsc(b, a); });
    else if (mode === 'az') arr.sort(function (a, b) { return (a.title || '').localeCompare(b.title || '', 'zh'); });
    else if (mode === 'za') arr.sort(function (a, b) { return (b.title || '').localeCompare(a.title || '', 'zh'); });
    return arr;
  }

  function activeFilterTags() {
    var f = state.filters, out = [];
    if (f.platform !== 'all') out.push('平台: ' + f.platform);
    if (f.genre !== 'all') out.push('类型: ' + f.genre);
    if (f.status !== 'all') out.push('状态: ' + (f.status === 'released' ? '已发售' : '即将推出'));
    if (f.year !== 'all') out.push('年份: ' + f.year);
    if (state.query.trim()) out.push('搜索: "' + state.query.trim() + '"');
    return out;
  }

  /* ---------------- formatting ---------------- */
  function formatDate(g) {
    if (!g.releaseDate) return '待定';
    if (g.releaseDateTBD) return g.releaseDate.slice(0, 4) + '年' + g.releaseDate.slice(5, 7) + '月 · 待定';
    var p = g.releaseDate.split('-');
    return p[0] + '.' + p[1] + '.' + p[2];
  }
  function statusLabel(s) { return s === 'released' ? '已发售' : '即将推出'; }

  /* ---------------- card factory ---------------- */
  function createCard(g) {
    var article = document.createElement('article');
    article.className = 'game-card';
    article.dataset.id = g.id;
    var colors = g.coverColors || ['#1a1f2b', '#2a3040'];
    article.innerHTML =
      '<div class="card-cover" style="background:linear-gradient(135deg,' + colors[0] + ',' + colors[1] + ')">' +
        '<div class="card-cover-fallback">' + escapeHtml(g.title) + '</div>' +
        '<span class="card-status ' + g.status + '">' + statusLabel(g.status) + '</span>' +
        '<button class="fav-btn' + (Fav.has(g.id) ? ' active' : '') + '" aria-label="收藏 ' + escapeHtml(g.title) + '">' + HEART + '</button>' +
        '<img src="' + escapeHtml(g.cover) + '" alt="' + escapeHtml(g.title) + ' 封面" loading="lazy" onerror="this.style.display=\'none\'">' +
      '</div>' +
      '<div class="card-body">' +
        '<h3 class="card-title">' + escapeHtml(g.title) + '</h3>' +
        '<p class="card-dev" title="' + escapeHtml(g.developer) + '">' + escapeHtml(g.developer) + '</p>' +
        '<div class="card-meta">' +
          '<span class="card-genre">' + escapeHtml((g.genres && g.genres[0]) || '游戏') + '</span>' +
          '<span class="card-date">' + escapeHtml(formatDate(g)) + '</span>' +
        '</div>' +
      '</div>';
    return article;
  }

  function renderGrid(containerId, list) {
    var c = $(containerId);
    if (!c) return;
    c.innerHTML = '';
    var frag = document.createDocumentFragment();
    list.forEach(function (g) { frag.appendChild(createCard(g)); });
    c.appendChild(frag);
  }

  /* ---------------- home render ---------------- */
  function renderHome() {
    var coming = sortGames(state.games.filter(function (g) { return g.status === 'coming-soon'; }), 'upcoming');
    var latest = sortGames(state.games.filter(function (g) { return g.status === 'released'; }), 'latest');
    var featured = FEATURED_IDS.map(gameById).filter(Boolean);
    if (featured.length < 4) featured = featured.concat(latest.slice(0, 4 - featured.length));

    renderGrid('featuredGrid', featured.slice(0, 4));
    renderGrid('comingGrid', coming.slice(0, 8));
    renderGrid('latestGrid', latest.slice(0, 8));

    // stats
    var stats = { total: state.games.length, genres: allGenres().length, coming: coming.length };
    document.querySelectorAll('.stat-num').forEach(function (el) {
      var k = el.dataset.stat;
      if (k && stats[k] != null) animateNumber(el, stats[k]);
    });

    // genre cloud
    var cloud = $('genreCloud');
    if (cloud) {
      cloud.innerHTML = '';
      allGenres().forEach(function (gn) {
        var count = state.games.filter(function (g) { return (g.genres || []).indexOf(gn) !== -1; }).length;
        var btn = document.createElement('button');
        btn.className = 'genre-chip';
        btn.dataset.genre = gn;
        btn.innerHTML = escapeHtml(gn) + ' <span class="g-count">' + count + '</span>';
        cloud.appendChild(btn);
      });
    }
  }

  function animateNumber(el, target) {
    var start = null, dur = 600;
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step); else el.textContent = target;
    }
    requestAnimationFrame(step);
  }

  /* ---------------- filter chips ---------------- */
  function renderFilterChips() {
    var groups = [
      { el: 'filterPlatform', key: 'platform', items: allPlatforms(), label: '全部平台' },
      { el: 'filterGenre', key: 'genre', items: allGenres(), label: '全部类型' },
      { el: 'filterStatus', key: 'status', items: [{ v: 'released', l: '已发售' }, { v: 'coming-soon', l: '即将推出' }], label: '全部状态' },
      { el: 'filterYear', key: 'year', items: allYears(), label: '全部年份' }
    ];
    groups.forEach(function (grp) {
      var box = $(grp.el);
      if (!box) return;
      box.innerHTML = '';
      var all = document.createElement('button');
      all.className = 'chip' + (state.filters[grp.key] === 'all' ? ' active' : '');
      all.dataset.filterKey = grp.key; all.dataset.filterVal = 'all';
      all.textContent = grp.label;
      box.appendChild(all);
      grp.items.forEach(function (it) {
        var v = typeof it === 'string' ? it : it.v;
        var l = typeof it === 'string' ? it : it.l;
        var b = document.createElement('button');
        b.className = 'chip' + (state.filters[grp.key] === v ? ' active' : '');
        b.dataset.filterKey = grp.key; b.dataset.filterVal = v;
        b.textContent = l;
        box.appendChild(b);
      });
    });
    var ft = $('filterToggle');
    if (ft) {
      var anyActive = Object.keys(state.filters).some(function (k) { return state.filters[k] !== 'all'; }) || !!state.query.trim();
      ft.classList.toggle('on', anyActive);
    }
  }

  /* ---------------- library render ---------------- */
  function renderLibrary() {
    var list = getFiltered();
    renderGrid('libraryGrid', list);
    var rc = $('resultCount');
    if (rc) rc.textContent = list.length + ' 款游戏';
    var empty = $('libraryEmpty');
    if (empty) empty.classList.toggle('hidden', list.length > 0);
    var grid = $('libraryGrid');
    if (grid) grid.classList.toggle('hidden', list.length === 0);
    var af = $('activeFilters');
    if (af) {
      af.innerHTML = '';
      activeFilterTags().forEach(function (t) {
        var s = document.createElement('span');
        s.className = 'active-tag'; s.textContent = t;
        af.appendChild(s);
      });
    }
    renderFilterChips();
    var ss = $('sortSelect');
    if (ss && ss.value !== state.sort) ss.value = state.sort;
    var ls = $('libSearch');
    if (ls && ls.value !== state.query) ls.value = state.query;
    var sc = $('searchClear');
    if (sc) sc.classList.toggle('hidden', !state.query);
  }

  /* ---------------- favorites render ---------------- */
  function renderFavorites() {
    var list = Array.from(state.favorites).map(gameById).filter(Boolean);
    list = sortGames(list, 'latest');
    renderGrid('favGrid', list);
    var fc = $('favCount');
    if (fc) fc.textContent = list.length + ' 款收藏';
    var empty = $('favEmpty');
    if (empty) empty.classList.toggle('hidden', list.length > 0);
    var grid = $('favGrid');
    if (grid) grid.classList.toggle('hidden', list.length === 0);
  }

  /* ---------------- detail render ---------------- */
  function renderDetail(id) {
    var box = $('detailContainer');
    var g = gameById(id);
    if (!box) return;
    if (!g) {
      box.innerHTML =
        '<div class="empty-state" style="min-height:50vh">' +
          '<h3>未找到该游戏</h3><p>ID ' + escapeHtml(id) + ' 不存在，可能已被移除。</p>' +
          '<a class="btn btn-primary" href="#/library">返回游戏库</a></div>';
      return;
    }
    var colors = g.coverColors || ['#1a1f2b', '#2a3040'];
    var tags = (g.tags || []).map(function (t) { return '<span class="tag-pill">' + escapeHtml(t) + '</span>'; }).join('');
    var siteBtn = g.website
      ? '<a class="btn-site" href="' + escapeHtml(g.website) + '" target="_blank" rel="noopener">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>' +
          '官方网站</a>' : '';
    box.innerHTML =
      '<div class="detail-wrap">' +
        '<a class="detail-back" href="#/library">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>返回游戏库</a>' +
        '<div class="detail-grid">' +
          '<div class="detail-cover" style="background:linear-gradient(135deg,' + colors[0] + ',' + colors[1] + ')">' +
            '<div class="card-cover-fallback" style="font-size:22px">' + escapeHtml(g.title) + '</div>' +
            '<img src="' + escapeHtml(g.cover) + '" alt="' + escapeHtml(g.title) + ' 封面" onerror="this.style.display=\'none\'">' +
          '</div>' +
          '<div class="detail-info">' +
            '<h1 class="detail-title">' + escapeHtml(g.title) + '</h1>' +
            '<div class="detail-status-line">' +
              '<span class="status-pill ' + g.status + '">' + statusLabel(g.status) + '</span>' +
              '<span class="detail-date">' + escapeHtml(formatDate(g)) + '</span>' +
            '</div>' +
            '<dl class="detail-fields">' +
              '<dt>开发商</dt><dd>' + escapeHtml(g.developer) + '</dd>' +
              '<dt>发行商</dt><dd>' + escapeHtml(g.publisher || '独立发行') + '</dd>' +
              '<dt>平台</dt><dd>' + escapeHtml((g.platforms || []).join(' · ')) + '</dd>' +
              '<dt>类型</dt><dd>' + escapeHtml((g.genres || []).join(' · ')) + '</dd>' +
            '</dl>' +
            '<div class="detail-tags">' + tags + '</div>' +
            '<p class="detail-desc">' + escapeHtml(g.description || '暂无简介。') + '</p>' +
            '<div class="detail-actions">' +
              '<button class="btn-fav' + (Fav.has(g.id) ? ' active' : '') + '" id="detailFavBtn" data-game-id="' + g.id + '">' +
                HEART + (Fav.has(g.id) ? '已收藏' : '加入收藏') + '</button>' +
              siteBtn +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    var df = $('detailFavBtn');
    if (df) {
      df.addEventListener('click', function () {
        Fav.toggle(g.id);
        df.classList.toggle('active', Fav.has(g.id));
        df.innerHTML = HEART + (Fav.has(g.id) ? '已收藏' : '加入收藏');
      });
    }
  }

  /* ---------------- router ---------------- */
  function parseHash() {
    var h = location.hash || '#/';
    var m = h.match(/^#(game-\d+)/);
    if (m) return { view: 'detail', id: m[1] };
    if (h.indexOf('#/library') === 0) {
      var q = {};
      var qi = h.indexOf('?');
      if (qi > -1) {
        h.slice(qi + 1).split('&').forEach(function (p) {
          var kv = p.split('=');
          q[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || '');
        });
      }
      return { view: 'library', query: q };
    }
    if (h.indexOf('#/favorites') === 0) return { view: 'favorites' };
    return { view: 'home' };
  }

  function showView(name) {
    state.currentView = name;
    ['home', 'library', 'favorites', 'detail'].forEach(function (v) {
      var sec = $('view-' + v);
      if (sec) sec.classList.toggle('hidden', v !== name);
    });
    document.querySelectorAll('.nav-link').forEach(function (a) {
      a.classList.toggle('active', a.dataset.nav === name);
    });
    var nl = $('navLinks'), nt = $('navToggle');
    if (nl) nl.classList.remove('open');
    if (nt) { nt.classList.remove('open'); nt.setAttribute('aria-expanded', 'false'); }
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  function route() {
    var r = parseHash();
    if (r.view === 'detail') { showView('detail'); renderDetail(r.id); return; }
    if (r.view === 'library') {
      if (r.query && r.query.sort) state.sort = r.query.sort;
      showView('library'); renderLibrary(); return;
    }
    if (r.view === 'favorites') { showView('favorites'); renderFavorites(); return; }
    showView('home'); renderHome();
  }

  /* ---------------- events ---------------- */
  function bindEvents() {
    // global click delegation: cards + fav buttons + chips + genre chips
    document.addEventListener('click', function (e) {
      var favBtn = e.target.closest('.fav-btn');
      if (favBtn) {
        e.stopPropagation();
        var card = favBtn.closest('.game-card');
        var id = card ? card.dataset.id : null;
        if (id) { Fav.toggle(id); if (state.currentView === 'favorites') renderFavorites(); }
        return;
      }
      var chip = e.target.closest('.chip[data-filter-key]');
      if (chip) {
        state.filters[chip.dataset.filterKey] = chip.dataset.filterVal;
        renderLibrary();
        return;
      }
      var genreChip = e.target.closest('.genre-chip');
      if (genreChip) {
        state.filters.genre = genreChip.dataset.genre;
        state.query = '';
        syncSearchInputs();
        location.hash = '#/library';
        return;
      }
      var cardEl = e.target.closest('.game-card');
      if (cardEl && cardEl.dataset.id) {
        location.hash = '#' + cardEl.dataset.id;
      }
    });

    // search inputs (hero + library)
    function onSearchInput(val, fromHero) {
      state.query = val;
      syncSearchInputs();
      if (fromHero && val.trim() && state.currentView === 'home') {
        location.hash = '#/library';
      } else if (state.currentView === 'library') {
        renderLibrary();
      }
    }
    var heroS = $('heroSearch'), libS = $('libSearch');
    if (heroS) heroS.addEventListener('input', function (e) { onSearchInput(e.target.value, true); });
    if (libS) libS.addEventListener('input', function (e) { onSearchInput(e.target.value, false); });

    var sc = $('searchClear');
    if (sc) sc.addEventListener('click', function () {
      state.query = ''; syncSearchInputs(); renderLibrary();
      var l = $('libSearch'); if (l) l.focus();
    });

    // "/" focuses search
    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) {
        e.preventDefault();
        var target = state.currentView === 'home' ? $('heroSearch') : $('libSearch');
        if (target) target.focus();
      }
      if (e.key === 'Escape' && state.currentView === 'detail') location.hash = '#/library';
    });

    // sort
    var ss = $('sortSelect');
    if (ss) ss.addEventListener('change', function (e) { state.sort = e.target.value; renderLibrary(); });

    // filter toggle (mobile) + reset
    var ft = $('filterToggle'), fp = $('filterPanel');
    if (ft && fp) {
      ft.addEventListener('click', function () {
        var open = fp.classList.toggle('open');
        ft.classList.toggle('open', open);
        ft.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }
    var fr = $('filterReset');
    if (fr) fr.addEventListener('click', resetAll);
    var er = $('emptyReset');
    if (er) er.addEventListener('click', resetAll);

    // mobile nav toggle
    var nt = $('navToggle'), nl = $('navLinks');
    if (nt && nl) {
      nt.addEventListener('click', function () {
        var open = nl.classList.toggle('open');
        nt.classList.toggle('open', open);
        nt.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }

    // retry button
    var rb = $('retryBtn');
    if (rb) rb.addEventListener('click', function () { location.reload(); });

    window.addEventListener('hashchange', route);
  }

  function syncSearchInputs() {
    var heroS = $('heroSearch'), libS = $('libSearch');
    if (heroS && heroS.value !== state.query) heroS.value = state.query;
    if (libS && libS.value !== state.query) libS.value = state.query;
    var sc = $('searchClear');
    if (sc) sc.classList.toggle('hidden', !state.query);
  }

  function resetAll() {
    state.query = '';
    state.filters = { platform: 'all', genre: 'all', status: 'all', year: 'all' };
    state.sort = 'latest';
    syncSearchInputs();
    renderLibrary();
  }

  /* ---------------- init ---------------- */
  function init() {
    Fav.load();
    Fav.updateBadge();
    bindEvents();
    loadGames()
      .then(function () {
        var ls = $('loadingScreen');
        if (ls) ls.classList.add('hidden');
        route();
      })
      .catch(function (err) {
        showError('无法读取 games.json（' + (err && err.message ? err.message : '网络错误') + '）。请确认文件存在后刷新。');
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
