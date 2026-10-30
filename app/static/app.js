'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  user: null, view: 'library', playlistId: null, playlists: [], tracks: [], total: 0,
  page: 1, pageSize: 30, search: '', queue: [], current: null, shuffle: false,
  repeat: 0, authMode: 'login', playlistEditing: null, addingTrack: null,
  editingTrack: null, status: null, requestId: 0, audioRequest: 0,
};
const audio = $('#audio');
let searchTimer;
let sessionNotice = false;
let previousVolume = 0.8;
let lastDialogFocus = null;

function icon(name, className = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', `icon ${className}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

function el(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== '') node.textContent = text;
  return node;
}

function toast(message, error = false) {
  const node = el('div', `toast${error ? ' error' : ''}`, message);
  $('#toasts').append(node);
  setTimeout(() => node.remove(), error ? 7000 : 4000);
}

function errorMessage(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const name = item.loc?.at(-1);
      if (name === 'password') return 'Пароль должен содержать от 12 до 128 символов.';
      if (name === 'username') return 'Имя: от 3 до 64 символов, латиница, цифры и подчёркивание.';
      return item.msg || fallback;
    }).filter((value, index, list) => list.indexOf(value) === index).join('\n');
  }
  return fallback;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (method !== 'GET' && state.user?.csrf_token) headers.set('X-CSRF-Token', state.user.csrf_token);
  let response;
  try {
    response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.');
  }
  const type = response.headers.get('content-type') || '';
  const data = type.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    if (response.status === 401 && state.user) {
      state.user = null;
      state.playlists = [];
      updateAccount();
      renderPlaylists();
      if (!sessionNotice) {
        toast('Сессия завершилась. Войдите ещё раз.', true);
        sessionNotice = true;
      }
    }
    const error = new Error(errorMessage(data?.detail, response.status === 413 ? 'Файл слишком большой.' : `Не удалось выполнить запрос (${response.status}).`));
    error.status = response.status;
    throw error;
  }
  return data;
}

function json(method, body) { return { method, body: JSON.stringify(body) }; }

function formatTime(seconds) {
  if (!Number.isFinite(Number(seconds)) || seconds < 0) return '0:00';
  const value = Math.floor(Number(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }).replace(' г.', '');
}

function pluralTracks(count) {
  const mod = count % 100;
  if (mod >= 11 && mod <= 14) return `${count} треков`;
  if (count % 10 === 1) return `${count} трек`;
  if (count % 10 >= 2 && count % 10 <= 4) return `${count} трека`;
  return `${count} треков`;
}

function cover(track, className = '') {
  const node = el('div', `cover ${className}`.trim());
  node.style.setProperty('--hue', String(((Number(track.id) || 0) * 47 + 65) % 360));
  node.setAttribute('aria-hidden', 'true');
  node.append(icon('wave'));
  return node;
}

function iconButton(name, label, callback, className = '') {
  const button = el('button', `icon-button ${className}`.trim());
  button.type = 'button';
  button.title = label;
  button.setAttribute('aria-label', label);
  button.append(icon(name));
  button.addEventListener('click', callback);
  return button;
}

function openDialog(id) {
  const dialog = $(id);
  if (dialog.open) return;
  lastDialogFocus = document.activeElement;
  dialog.showModal();
  $('#account-menu').hidden = true;
  closeMenus();
}

function closeDialog(dialog) { dialog.close(); }

$$('dialog').forEach((dialog) => {
  $('[data-close]', dialog)?.addEventListener('click', () => closeDialog(dialog));
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeDialog(dialog);
  });
  dialog.addEventListener('close', () => {
    if (lastDialogFocus?.isConnected) lastDialogFocus.focus();
  });
});

function requireUser(callback) {
  if (!state.user) { showAuth('login'); return false; }
  callback?.();
  return true;
}

function updateAccount() {
  $('#auth-button').hidden = Boolean(state.user);
  $('#account').hidden = !state.user;
  if (state.user) {
    $('#username').textContent = state.user.username;
    $('#avatar').textContent = state.user.username.slice(0, 1).toUpperCase();
  }
  $('#account-menu').hidden = true;
  $('#account-button').setAttribute('aria-expanded', 'false');
}

function showAuth(mode = 'login') {
  state.authMode = mode;
  const register = mode === 'register';
  $('#auth-title').textContent = register ? 'Будьте на своей волне' : 'С возвращением';
  $('#auth-description').textContent = register ? 'Создайте аккаунт. Добавляйте музыку. Слушайте своё.' : 'Войдите, чтобы собрать свою коллекцию.';
  $('#auth-submit').replaceChildren(document.createTextNode(register ? 'Создать аккаунт' : 'Войти'), icon('arrow'));
  $('#auth-switch-copy').textContent = register ? 'Уже есть аккаунт?' : 'Ещё нет аккаунта?';
  $('#auth-switch').textContent = register ? 'Войти' : 'Создать аккаунт';
  $('#auth-form [name=password]').autocomplete = register ? 'new-password' : 'current-password';
  $('#auth-error').textContent = '';
  openDialog('#auth-dialog');
}

$('#auth-button').addEventListener('click', () => showAuth());
$('#auth-switch').addEventListener('click', () => showAuth(state.authMode === 'login' ? 'register' : 'login'));
$('#auth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#auth-submit');
  button.disabled = true;
  $('#auth-error').textContent = '';
  try {
    const values = new FormData(event.currentTarget);
    const result = await api(`/auth/${state.authMode}`, json('POST', { username: values.get('username').trim(), password: values.get('password') }));
    state.user = result?.csrf_token ? result : await api('/auth/me');
    sessionNotice = false;
    updateAccount();
    $('#auth-form [name=password]').value = '';
    closeDialog($('#auth-dialog'));
    toast(state.authMode === 'register' ? 'Добро пожаловать на ВОЛНУ!' : 'Вы снова на своей волне.');
    await loadPlaylists();
    await loadTracks();
  } catch (error) { $('#auth-error').textContent = error.message; }
  finally { button.disabled = false; }
});

$('#account-button').addEventListener('click', () => {
  $('#account-menu').hidden = !$('#account-menu').hidden;
  $('#account-button').setAttribute('aria-expanded', String(!$('#account-menu').hidden));
});

$('#logout-button').addEventListener('click', async () => {
  try {
    await api('/auth/logout', { method: 'POST' });
    state.user = null;
    state.playlists = [];
    updateAccount();
    renderPlaylists();
    changeView('library');
    toast('Вы вышли из аккаунта.');
  } catch (error) { toast(error.message, true); }
});

function closeSidebar() {
  $('#sidebar').classList.remove('open');
  $('#sidebar-scrim').classList.remove('visible');
  $('#mobile-menu').setAttribute('aria-expanded', 'false');
}

$('#mobile-menu').addEventListener('click', () => {
  const open = $('#sidebar').classList.toggle('open');
  $('#sidebar-scrim').classList.toggle('visible', open);
  $('#mobile-menu').setAttribute('aria-expanded', String(open));
});
$('#sidebar-scrim').addEventListener('click', closeSidebar);
$$('[data-view]').forEach((button) => button.addEventListener('click', () => changeView(button.dataset.view)));

function changeView(view, playlistId = null) {
  if (view !== 'library' && !requireUser()) return;
  state.view = view;
  state.playlistId = playlistId;
  state.page = 1;
  state.search = '';
  $('#search').value = '';
  closeSidebar();
  closeMenus();
  updateView();
  loadTracks();
}

function updateView() {
  const playlist = state.playlists.find((item) => item.id === state.playlistId);
  const views = {
    library: ['ОТКРЫТАЯ КОЛЛЕКЦИЯ', 'Вся музыка', 'Свежие треки от тех, кто любит музыку'],
    mine: ['ЛИЧНАЯ КОЛЛЕКЦИЯ', 'Мои треки', 'Ваш звук. Ваше место. Ваша коллекция.'],
    favorites: ['ВСЕГДА ПОД РУКОЙ', 'Любимое', 'Треки, к которым хочется возвращаться'],
    playlist: ['ВАШ ПЛЕЙЛИСТ', playlist?.name || 'Плейлист', 'Музыка, которую вы собрали вместе'],
  };
  const config = views[state.view] || views.library;
  $('#hero').hidden = state.view !== 'library' || Boolean(state.search);
  $('#view-eyebrow').textContent = state.search ? 'РЕЗУЛЬТАТЫ ПОИСКА' : config[0];
  $('#view-title').replaceChildren(document.createTextNode(state.search ? 'Нашлось на волне' : config[1]), el('span', 'count-badge', String(state.total)));
  $('#view-title .count-badge').id = 'track-total';
  $('#view-description').textContent = state.search ? `По запросу «${state.search}»` : config[2];
  $('#collection-caption').textContent = state.view === 'library' ? 'Все треки' : 'Ваша коллекция';
  $('#playlist-rename').hidden = state.view !== 'playlist';
  $('#playlist-delete').hidden = state.view !== 'playlist';
  $$('[data-view]').forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  renderPlaylists();
  document.title = `${state.search ? 'Поиск' : config[1]} — ВОЛНА`;
}

$('#search').addEventListener('input', (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = event.target.value.trim();
    state.page = 1;
    updateView();
    loadTracks();
  }, 280);
});

async function loadTracks() {
  const requestId = ++state.requestId;
  $('#loading-state').hidden = false;
  $('#empty-state').hidden = true;
  $('#error-state').hidden = true;
  $('#track-table').hidden = true;
  $('#pagination').hidden = true;
  $('#play-all').disabled = true;
  try {
    let path;
    const params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
    if (state.search) params.set('search', state.search);
    if (state.view === 'mine') params.set('mine', 'true');
    if (state.view === 'favorites') params.set('favorites', 'true');
    path = state.view === 'playlist' ? `/api/playlists/${state.playlistId}/tracks?${params}` : `/api/tracks?${params}`;
    const data = await api(path);
    if (requestId !== state.requestId) return;
    state.tracks = Array.isArray(data) ? data : (data.tracks || []);
    if (state.view === 'playlist') {
      // Playlists are bounded collections; their endpoint returns the entire list.
      if (state.search) state.tracks = state.tracks.filter((track) => `${track.name} ${track.artist}`.toLowerCase().includes(state.search.toLowerCase()));
      state.total = state.tracks.length;
      state.tracks = state.tracks.slice((state.page - 1) * state.pageSize, state.page * state.pageSize);
    } else {
      state.total = Array.isArray(data) ? state.tracks.length : (data.total ?? state.tracks.length);
    }
    $('#track-total').textContent = String(state.total);
    $('#collection-caption').textContent = pluralTracks(state.total);
    $('#loading-state').hidden = true;
    renderTracks();
  } catch (error) {
    if (requestId !== state.requestId) return;
    $('#loading-state').hidden = true;
    $('#error-state').hidden = false;
    $('#load-error').textContent = error.message;
  }
}

function renderTracks() {
  const list = $('#track-list');
  list.replaceChildren();
  $('#track-table').hidden = !state.tracks.length;
  $('#empty-state').hidden = Boolean(state.tracks.length);
  $('#play-all').disabled = !state.tracks.length;
  if (!state.tracks.length) renderEmptyState();
  state.tracks.forEach((track, index) => list.append(trackRow(track, index)));
  const pages = Math.ceil(state.total / state.pageSize);
  $('#pagination').hidden = pages <= 1;
  $('#page-prev').disabled = state.page <= 1;
  $('#page-next').disabled = state.page >= pages;
  $('#page-label').textContent = `${state.page} / ${pages || 1}`;
}

function renderEmptyState() {
  let title = 'У вашей коллекции ещё нет первого трека';
  let description = 'Загрузите музыку — и пусть здесь появится ваш звук.';
  let action = 'Загрузить первый трек';
  if (state.search) {
    title = 'Пока ничего не нашлось';
    description = 'Попробуйте другое название или имя исполнителя.';
    action = 'Сбросить поиск';
  } else if (state.view === 'favorites') {
    title = 'Здесь будут ваши любимые треки';
    description = 'Нажмите на сердечко рядом с треком, чтобы сохранить его.';
    action = 'Найти любимое';
  } else if (state.view === 'playlist') {
    title = 'Хорошему плейлисту нужен первый трек';
    description = 'Найдите музыку в обзоре и добавьте её с помощью «+» рядом с треком.';
    action = 'Перейти к музыке';
  } else if (state.view === 'mine') {
    title = 'Начните свою музыкальную коллекцию';
    description = 'Загруженные вами треки появятся здесь.';
    action = 'Добавить трек';
  }
  $('#empty-title').textContent = title;
  $('#empty-description').textContent = description;
  $('#empty-action').replaceChildren(document.createTextNode(action), icon(state.search ? 'close' : ['favorites', 'playlist'].includes(state.view) ? 'arrow' : 'plus'));
}

$('#empty-action').addEventListener('click', () => {
  if (state.search) {
    state.search = '';
    $('#search').value = '';
    state.page = 1;
    updateView();
    loadTracks();
  } else if (['favorites', 'playlist'].includes(state.view)) changeView('library');
  else showUpload();
});
$('#retry-button').addEventListener('click', loadTracks);
$('#page-prev').addEventListener('click', () => { state.page--; loadTracks(); });
$('#page-next').addEventListener('click', () => { state.page++; loadTracks(); });

function trackRow(track, index) {
  const row = el('div', 'track-row');
  row.dataset.trackId = String(track.id);
  row.classList.toggle('is-current', state.current?.id === track.id);
  const number = el('button', 'track-number');
  number.type = 'button';
  number.setAttribute('aria-label', `Слушать ${track.name}`);
  number.append(el('span', 'track-index', String((state.page - 1) * state.pageSize + index + 1)), icon(state.current?.id === track.id && !audio.paused ? 'pause' : 'play'));
  number.addEventListener('click', () => playFromList(track));
  const main = el('div', 'track-main');
  const info = el('div', 'track-info');
  const name = el('button', 'track-name', track.name);
  name.type = 'button';
  name.title = track.name;
  name.addEventListener('click', () => playFromList(track));
  const artist = el('span', 'track-artist', track.artist || 'Неизвестный исполнитель');
  artist.title = track.artist || '';
  info.append(name, artist);
  main.append(cover(track), info);
  const date = el('span', 'track-date date-column', formatDate(track.created_at));
  const duration = el('span', 'track-duration', formatTime(track.duration));
  const actions = el('div', 'track-actions');
  const favorite = iconButton('heart', track.is_favorite ? 'Убрать из любимого' : 'В любимое', () => toggleFavorite(track), 'favorite');
  favorite.dataset.favoriteId = String(track.id);
  favorite.setAttribute('aria-pressed', String(Boolean(track.is_favorite)));
  const add = iconButton('plus', 'Добавить в плейлист', () => showAddToPlaylist(track), 'add-to-playlist');
  const more = el('div', 'track-more');
  const moreButton = iconButton('more', `Действия с треком ${track.name}`, () => {
    const shouldOpen = menu.hidden;
    closeMenus();
    menu.hidden = !shouldOpen;
    moreButton.setAttribute('aria-expanded', String(shouldOpen));
    if (shouldOpen) $('button', menu)?.focus();
  });
  moreButton.setAttribute('aria-expanded', 'false');
  const menu = el('div', 'track-menu');
  menu.hidden = true;
  const menuItem = (label, callback, danger = false) => {
    const button = el('button', danger ? 'danger' : '', label);
    button.type = 'button';
    button.addEventListener('click', () => { closeMenus(); callback(); });
    menu.append(button);
  };
  menuItem('Добавить в плейлист', () => showAddToPlaylist(track));
  if (state.view === 'playlist') menuItem('Убрать из плейлиста', () => removeFromPlaylist(track));
  if (state.user && track.owner_id === state.user.id) {
    menuItem('Изменить название', () => showEdit(track));
    menuItem('Удалить трек', () => deleteTrack(track), true);
  }
  more.append(moreButton, menu);
  actions.append(favorite, add, more);
  row.append(number, main, date, duration, actions);
  return row;
}

function closeMenus() {
  $$('.track-menu').forEach((menu) => { menu.hidden = true; });
  $$('.track-more [aria-expanded]').forEach((button) => button.setAttribute('aria-expanded', 'false'));
}

document.addEventListener('click', (event) => {
  if (!event.target.closest('.track-more')) closeMenus();
  if (!event.target.closest('.account')) {
    $('#account-menu').hidden = true;
    $('#account-button').setAttribute('aria-expanded', 'false');
  }
});

async function toggleFavorite(track) {
  if (!requireUser()) return;
  const buttons = $$(`[data-favorite-id="${Number(track.id)}"]`);
  buttons.forEach((button) => { button.disabled = true; });
  try {
    await api(`/api/tracks/${track.id}/favorite`, { method: track.is_favorite ? 'DELETE' : 'PUT' });
    const value = !track.is_favorite;
    [state.tracks, state.queue, state.current ? [state.current] : []].forEach((collection) => collection.forEach((item) => { if (item.id === track.id) item.is_favorite = value; }));
    track.is_favorite = value;
    if (state.view === 'favorites' && !value) await loadTracks(); else renderTracks();
    updatePlayer();
  } catch (error) { toast(error.message, true); }
  finally { buttons.forEach((button) => { button.disabled = false; }); }
}

async function loadPlaylists() {
  if (!state.user) { renderPlaylists(); return; }
  try {
    const data = await api('/api/playlists');
    state.playlists = Array.isArray(data) ? data : (data.playlists || []);
    renderPlaylists();
  } catch (error) { toast(error.message, true); }
}

function renderPlaylists() {
  const nav = $('#playlist-nav');
  nav.replaceChildren();
  if (!state.playlists.length) {
    nav.append(el('p', 'sidebar-hint', state.user ? 'Первый плейлист начинается с настроения' : 'Войдите, чтобы собрать свои плейлисты'));
    return;
  }
  state.playlists.forEach((playlist) => {
    const button = el('button', 'nav-item');
    button.type = 'button';
    const active = state.view === 'playlist' && state.playlistId === playlist.id;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    button.title = playlist.name;
    button.append(icon('list'), el('span', '', playlist.name));
    button.addEventListener('click', () => changeView('playlist', playlist.id));
    nav.append(button);
  });
}

function showPlaylistDialog(playlist = null, addingTrack = null) {
  if (!requireUser()) return;
  state.playlistEditing = playlist;
  state.addingTrack = addingTrack;
  $('#playlist-dialog-title').textContent = playlist ? 'Новое имя плейлиста' : 'Новый плейлист';
  $('#playlist-form [name=name]').value = playlist?.name || '';
  $('#playlist-error').textContent = '';
  openDialog('#playlist-dialog');
}

$('#new-playlist').addEventListener('click', () => showPlaylistDialog());
$('#playlist-rename').addEventListener('click', () => showPlaylistDialog(state.playlists.find((item) => item.id === state.playlistId)));
$('#playlist-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('[type=submit]', event.currentTarget);
  const name = event.currentTarget.elements.name.value.trim();
  if (!name) return;
  button.disabled = true;
  $('#playlist-error').textContent = '';
  try {
    const editing = state.playlistEditing;
    const result = await api(editing ? `/api/playlists/${editing.id}` : '/api/playlists', json(editing ? 'PATCH' : 'POST', { name }));
    await loadPlaylists();
    closeDialog($('#playlist-dialog'));
    if (state.addingTrack && !editing) {
      if (result?.id) {
        await api(`/api/playlists/${result.id}/tracks/${state.addingTrack.id}`, { method: 'PUT' });
        state.addingTrack = null;
        await loadPlaylists();
        toast('Трек добавлен в новый плейлист.');
      }
    } else if (editing) {
      updateView();
      toast('Название плейлиста сохранено.');
    } else {
      toast('Новый плейлист готов.');
      if (result?.id) changeView('playlist', result.id);
    }
  } catch (error) { $('#playlist-error').textContent = error.message; }
  finally { button.disabled = false; }
});

$('#playlist-delete').addEventListener('click', async () => {
  const playlist = state.playlists.find((item) => item.id === state.playlistId);
  if (!playlist || !confirm(`Удалить плейлист «${playlist.name}»? Сами треки останутся в коллекции.`)) return;
  try {
    await api(`/api/playlists/${playlist.id}`, { method: 'DELETE' });
    await loadPlaylists();
    changeView('library');
    toast('Плейлист удалён.');
  } catch (error) { toast(error.message, true); }
});

async function showAddToPlaylist(track) {
  if (!requireUser()) return;
  state.addingTrack = track;
  await loadPlaylists();
  $('#add-track-name').textContent = `${track.name} · ${track.artist || 'Неизвестный исполнитель'}`;
  const list = $('#add-playlist-list');
  list.replaceChildren();
  if (!state.playlists.length) list.append(el('p', 'queue-empty', 'Пока нет плейлистов. Создайте первый — и мы добавим в него этот трек.'));
  state.playlists.forEach((playlist) => {
    const button = el('button', 'playlist-choice');
    button.type = 'button';
    button.append(icon('list'), el('span', '', playlist.name), el('small', '', pluralTracks(playlist.track_count || 0)));
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api(`/api/playlists/${playlist.id}/tracks/${track.id}`, { method: 'PUT' });
        state.addingTrack = null;
        closeDialog($('#add-dialog'));
        toast(`Трек в плейлисте «${playlist.name}».`);
        await loadPlaylists();
        if (state.view === 'playlist' && state.playlistId === playlist.id) await loadTracks();
      } catch (error) { toast(error.message, true); }
      finally { button.disabled = false; }
    });
    list.append(button);
  });
  openDialog('#add-dialog');
}

$('#add-new-playlist').addEventListener('click', () => {
  const track = state.addingTrack;
  closeDialog($('#add-dialog'));
  showPlaylistDialog(null, track);
});

async function removeFromPlaylist(track) {
  try {
    await api(`/api/playlists/${state.playlistId}/tracks/${track.id}`, { method: 'DELETE' });
    await Promise.all([loadTracks(), loadPlaylists()]);
    toast('Трек убран из плейлиста.');
  } catch (error) { toast(error.message, true); }
}

async function refreshStatus() {
  try {
    state.status = await api('/api/status');
    const max = state.status.max_upload_mb || 25;
    $('#max-mb').textContent = String(max);
    $('#file-hint').textContent = `Один файл, до ${max} МБ`;
    $('#upload-status').textContent = state.status.uploads_ready ? '' : state.status.upload_message || 'Загрузка пока недоступна. Попробуйте позже.';
    $('#upload-submit').disabled = !state.status.uploads_ready;
  } catch (error) {
    state.status = null;
    $('#upload-status').textContent = 'Не удалось проверить доступность загрузки. Можно попробовать отправить файл.';
    $('#upload-submit').disabled = false;
  }
}

function showUpload() {
  if (!requireUser()) return;
  $('#upload-error').textContent = '';
  openDialog('#upload-dialog');
  refreshStatus();
}

['#upload-top', '#hero-upload'].forEach((selector) => $(selector).addEventListener('click', showUpload));

function selectedFile(file) {
  if (!file) return;
  const max = state.status?.max_upload_mb || 25;
  if (!file.name.toLowerCase().endsWith('.mp3')) {
    $('#upload-error').textContent = 'Пожалуйста, выберите файл MP3.';
    $('#upload-file').value = '';
    return;
  }
  if (file.size > max * 1024 * 1024) {
    $('#upload-error').textContent = `Файл больше ${max} МБ. Выберите трек поменьше.`;
    $('#upload-file').value = '';
    return;
  }
  $('#upload-error').textContent = '';
  $('#file-label').textContent = file.name;
  $('#file-hint').textContent = `${(file.size / 1024 / 1024).toFixed(1)} МБ · MP3`;
  const name = $('#upload-form [name=name]');
  if (!name.value) name.value = file.name.replace(/\.mp3$/i, '').slice(0, 120);
}

$('#upload-file').addEventListener('change', (event) => selectedFile(event.target.files[0]));
['dragenter', 'dragover'].forEach((name) => $('#dropzone').addEventListener(name, (event) => {
  event.preventDefault();
  $('#dropzone').classList.add('dragging');
}));
['dragleave', 'drop'].forEach((name) => $('#dropzone').addEventListener(name, (event) => {
  event.preventDefault();
  $('#dropzone').classList.remove('dragging');
}));
$('#dropzone').addEventListener('drop', (event) => {
  const files = event.dataTransfer.files;
  if (files.length !== 1) { $('#upload-error').textContent = 'Добавляйте по одному треку.'; return; }
  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  $('#upload-file').files = transfer.files;
  selectedFile(files[0]);
});

$('#upload-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = $('#upload-file').files[0];
  if (!file) { $('#upload-error').textContent = 'Сначала выберите MP3.'; return; }
  const form = event.currentTarget;
  const data = new FormData(form);
  data.set('name', data.get('name').trim());
  data.set('artist', data.get('artist').trim());
  if (!data.get('name') || !data.get('artist')) { $('#upload-error').textContent = 'Укажите название трека и исполнителя.'; return; }
  const button = $('#upload-submit');
  button.disabled = true;
  button.replaceChildren(el('span', 'spinner'), document.createTextNode('Загружаем и проверяем…'));
  $('#upload-error').textContent = '';
  try {
    await api('/api/tracks', { method: 'POST', body: data });
    form.reset();
    $('#file-label').textContent = 'Выберите MP3 или перетащите сюда';
    $('#file-hint').textContent = `Один файл, до ${state.status?.max_upload_mb || 25} МБ`;
    closeDialog($('#upload-dialog'));
    toast('Трек проверен и добавлен. Самое время послушать!');
    changeView('mine');
  } catch (error) { $('#upload-error').textContent = error.message; }
  finally {
    button.disabled = state.status?.uploads_ready === false;
    button.replaceChildren(icon('upload'), document.createTextNode('Загрузить трек'));
  }
});

function showEdit(track) {
  state.editingTrack = track;
  $('#edit-form [name=name]').value = track.name;
  $('#edit-form [name=artist]').value = track.artist || '';
  $('#edit-error').textContent = '';
  openDialog('#edit-dialog');
}

$('#edit-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $('[type=submit]', form);
  const values = { name: form.elements.name.value.trim(), artist: form.elements.artist.value.trim() };
  if (!values.name || !values.artist) return;
  button.disabled = true;
  try {
    await api(`/api/tracks/${state.editingTrack.id}`, json('PATCH', values));
    [state.queue, state.current ? [state.current] : []].forEach((collection) => collection.forEach((track) => { if (track.id === state.editingTrack.id) Object.assign(track, values); }));
    updatePlayer();
    closeDialog($('#edit-dialog'));
    await loadTracks();
    toast('Название сохранено.');
  } catch (error) { $('#edit-error').textContent = error.message; }
  finally { button.disabled = false; }
});

async function deleteTrack(track) {
  if (!confirm(`Удалить трек «${track.name}»? Он исчезнет из общей коллекции и всех плейлистов.`)) return;
  try {
    await api(`/api/tracks/${track.id}`, { method: 'DELETE' });
    if (state.current?.id === track.id) stopAudio();
    state.queue = state.queue.filter((item) => item.id !== track.id);
    if (state.tracks.length === 1 && state.page > 1) state.page--;
    await Promise.all([loadTracks(), loadPlaylists()]);
    renderQueue();
    toast('Трек удалён.');
  } catch (error) { toast(error.message, true); }
}

function playFromList(track) {
  if (state.current?.id === track.id) { togglePlayback(); return; }
  state.queue = [...state.tracks];
  playTrack(track);
}

async function playTrack(track) {
  const requestId = ++state.audioRequest;
  state.current = track;
  audio.src = `/api/tracks/${encodeURIComponent(track.id)}/stream`;
  audio.load();
  updatePlayer();
  renderQueue();
  try {
    await audio.play();
  } catch (error) {
    if (requestId !== state.audioRequest || error.name === 'AbortError') return;
    if (error.name === 'NotAllowedError') toast('Нажмите кнопку воспроизведения, чтобы включить музыку.');
    else if (!audio.error) toast('Не удалось включить трек. Попробуйте ещё раз.', true);
  }
}

async function togglePlayback() {
  if (!state.current) return;
  if (!audio.paused) { audio.pause(); return; }
  try { await audio.play(); }
  catch (error) { if (error.name !== 'AbortError') toast('Не удалось включить трек. Проверьте соединение.', true); }
}

function updatePlayer() {
  const track = state.current;
  $('#player-title').textContent = track?.name || 'Поймайте свою волну';
  $('#player-artist').textContent = track?.artist || (track ? 'Неизвестный исполнитель' : 'Выберите трек, чтобы начать');
  $('#player-cover').style.setProperty('--hue', String(((Number(track?.id) || 0) * 47 + 65) % 360));
  $('#player-favorite').disabled = !track;
  $('#player-favorite').setAttribute('aria-pressed', String(Boolean(track?.is_favorite)));
  $('#player-favorite').setAttribute('aria-label', track?.is_favorite ? 'Убрать текущий трек из любимого' : 'Добавить текущий трек в любимое');
  ['#play-pause', '#previous', '#next'].forEach((selector) => { $(selector).disabled = !track; });
  const playing = track && !audio.paused;
  $('#play-pause use').setAttribute('href', `#i-${playing ? 'pause' : 'play'}`);
  $('#play-pause').setAttribute('aria-label', playing ? 'Приостановить' : 'Воспроизвести');
  $$('.track-row').forEach((row) => {
    const current = Number(row.dataset.trackId) === track?.id;
    row.classList.toggle('is-current', current);
    $('.track-number use', row).setAttribute('href', `#i-${current && playing ? 'pause' : 'play'}`);
  });
  $('#duration').textContent = formatTime(Number.isFinite(audio.duration) ? audio.duration : track?.duration || 0);
  if ('mediaSession' in navigator && track && 'MediaMetadata' in window) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: track.name, artist: track.artist || '', album: 'ВОЛНА' });
    navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
  }
}

function stopAudio() {
  state.audioRequest++;
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  state.current = null;
  state.queue = [];
  $('#elapsed').textContent = '0:00';
  $('#seek').value = '0';
  $('#seek').disabled = true;
  $('#seek').style.setProperty('--fill', '0%');
  updatePlayer();
  renderQueue();
}

function nextTrack(direction = 1, automatic = false) {
  if (!state.queue.length || !state.current) return;
  const index = state.queue.findIndex((track) => track.id === state.current.id);
  if (direction < 0 && audio.currentTime > 3) { audio.currentTime = 0; return; }
  if (automatic && state.repeat === 2) { audio.currentTime = 0; audio.play().catch(() => {}); return; }
  let next;
  if (state.shuffle && state.queue.length > 1) {
    const options = state.queue.filter((track) => track.id !== state.current.id);
    next = options[Math.floor(Math.random() * options.length)];
  } else {
    let nextIndex = index + direction;
    if (nextIndex >= state.queue.length || nextIndex < 0) {
      if (automatic && state.repeat === 0) { audio.pause(); updatePlayer(); return; }
      nextIndex = (nextIndex + state.queue.length) % state.queue.length;
    }
    next = state.queue[nextIndex];
  }
  if (next) playTrack(next);
}

$('#play-all').addEventListener('click', () => {
  if (!state.tracks.length) return;
  state.queue = [...state.tracks];
  playTrack(state.shuffle ? state.queue[Math.floor(Math.random() * state.queue.length)] : state.queue[0]);
});
$('#play-pause').addEventListener('click', togglePlayback);
$('#previous').addEventListener('click', () => nextTrack(-1));
$('#next').addEventListener('click', () => nextTrack());
$('#player-favorite').addEventListener('click', () => { if (state.current) toggleFavorite(state.current); });
$('#shuffle').addEventListener('click', () => {
  state.shuffle = !state.shuffle;
  $('#shuffle').setAttribute('aria-pressed', String(state.shuffle));
  $('#queue-shuffle').setAttribute('aria-pressed', String(state.shuffle));
  toast(state.shuffle ? 'Случайный порядок включён.' : 'Случайный порядок выключен.');
});
$('#repeat').addEventListener('click', () => {
  state.repeat = (state.repeat + 1) % 3;
  $('#repeat').setAttribute('aria-pressed', String(state.repeat > 0));
  $('#queue-repeat').setAttribute('aria-pressed', String(state.repeat > 0));
  const descriptions = ['Повтор выключен', 'Повтор очереди', 'Повтор трека'];
  $('#repeat').setAttribute('aria-label', descriptions[state.repeat]);
  $('#queue-repeat').setAttribute('aria-label', descriptions[state.repeat]);
  $('#repeat').title = descriptions[state.repeat];
  $('#repeat-one').hidden = state.repeat !== 2;
  toast(descriptions[state.repeat]);
});
$('#queue-shuffle').addEventListener('click', () => $('#shuffle').click());
$('#queue-repeat').addEventListener('click', () => $('#repeat').click());

audio.volume = 0.8;
$('#volume').addEventListener('input', (event) => {
  const value = Number(event.target.value);
  audio.volume = value;
  audio.muted = false;
  event.target.style.setProperty('--fill', `${value * 100}%`);
  $('#mute').setAttribute('aria-label', value === 0 ? 'Включить звук' : 'Выключить звук');
});
$('#queue-volume').addEventListener('input', (event) => {
  $('#volume').value = event.target.value;
  $('#volume').dispatchEvent(new Event('input'));
});
audio.addEventListener('volumechange', () => {
  const value = audio.muted ? 0 : audio.volume;
  $('#queue-volume').value = String(value);
  $('#queue-volume').style.setProperty('--fill', `${value * 100}%`);
});
$('#mute').addEventListener('click', () => {
  if (audio.muted || audio.volume === 0) {
    audio.muted = false;
    audio.volume = previousVolume || 0.8;
  } else {
    previousVolume = audio.volume;
    audio.muted = true;
  }
  const value = audio.muted ? 0 : audio.volume;
  $('#volume').value = String(value);
  $('#volume').style.setProperty('--fill', `${value * 100}%`);
  $('#mute').setAttribute('aria-label', value === 0 ? 'Включить звук' : 'Выключить звук');
});
$('#seek').addEventListener('input', (event) => {
  if (Number.isFinite(audio.duration) && audio.duration > 0) {
    audio.currentTime = audio.duration * Number(event.target.value) / 100;
    event.target.style.setProperty('--fill', `${event.target.value}%`);
    $('#elapsed').textContent = formatTime(audio.currentTime);
  }
});
audio.addEventListener('timeupdate', () => {
  $('#elapsed').textContent = formatTime(audio.currentTime);
  const percent = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.currentTime / audio.duration * 100 : 0;
  $('#seek').value = String(percent);
  $('#seek').style.setProperty('--fill', `${percent}%`);
});
audio.addEventListener('loadedmetadata', () => {
  $('#seek').disabled = !Number.isFinite(audio.duration) || audio.duration <= 0;
  $('#duration').textContent = formatTime(audio.duration);
});
audio.addEventListener('play', updatePlayer);
audio.addEventListener('pause', updatePlayer);
audio.addEventListener('ended', () => nextTrack(1, true));
audio.addEventListener('error', () => {
  if (state.current && audio.getAttribute('src')) {
    toast('Трек недоступен или не удалось загрузить аудио. Попробуйте другой трек.', true);
    updatePlayer();
  }
});

function renderQueue() {
  const list = $('#queue-list');
  list.replaceChildren();
  if (!state.queue.length) { list.append(el('p', 'queue-empty', 'Выберите трек или нажмите «Слушать», чтобы собрать очередь.')); return; }
  state.queue.forEach((track, index) => {
    const button = el('button', `queue-track${state.current?.id === track.id ? ' active' : ''}`);
    const info = el('span', 'track-info');
    info.append(el('span', 'track-name', track.name), el('span', 'track-artist', track.artist || 'Неизвестный исполнитель'));
    button.append(cover(track), info, el('span', 'track-duration', formatTime(track.duration)));
    button.type = 'button';
    button.setAttribute('aria-label', `Слушать ${track.name}`);
    button.addEventListener('click', () => playTrack(state.queue[index]));
    list.append(button);
  });
}
$('#queue-button').addEventListener('click', () => {
  $('#queue-panel').hidden = !$('#queue-panel').hidden;
  $('#queue-button').setAttribute('aria-expanded', String(!$('#queue-panel').hidden));
  renderQueue();
});
$('#close-queue').addEventListener('click', () => {
  $('#queue-panel').hidden = true;
  $('#queue-button').setAttribute('aria-expanded', 'false');
  $('#queue-button').focus();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeMenus();
    closeSidebar();
    $('#account-menu').hidden = true;
    $('#queue-panel').hidden = true;
    $('#queue-button').setAttribute('aria-expanded', 'false');
  }
  const editing = event.target.closest('input,textarea,select,[contenteditable=true]');
  if (editing || $('dialog[open]') || event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === '/') { event.preventDefault(); $('#search').focus(); }
  if (event.code === 'Space' && state.current && !event.target.closest('button,a')) { event.preventDefault(); togglePlayback(); }
});

if ('mediaSession' in navigator) {
  [['play', () => audio.play()], ['pause', () => audio.pause()], ['previoustrack', () => nextTrack(-1)], ['nexttrack', () => nextTrack()]].forEach(([action, handler]) => {
    try { navigator.mediaSession.setActionHandler(action, handler); } catch (_) { /* Platform may omit a media action. */ }
  });
}

async function init() {
  updateView();
  renderQueue();
  const userRequest = api('/auth/me').then((user) => { state.user = user; updateAccount(); }).catch((error) => {
    if (error.status !== 401) toast('Не удалось проверить аккаунт. Попробуйте войти ещё раз.', true);
    state.user = null;
    updateAccount();
  });
  const statusRequest = refreshStatus();
  await userRequest;
  await Promise.all([loadTracks(), loadPlaylists(), statusRequest]);
}

init();
