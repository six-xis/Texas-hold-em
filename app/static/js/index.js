const nicknameInput = document.querySelector("#nickname");
const roomCodeInput = document.querySelector("#room-code");
const smallBlindInput = document.querySelector("#small-blind");
const bigBlindInput = document.querySelector("#big-blind");
const aiDefaultInput = document.querySelector("#ai-default");
const createButton = document.querySelector("#create-room");
const joinButton = document.querySelector("#join-room");
const registerButton = document.querySelector("#register-user");
const refreshRoomsButton = document.querySelector("#refresh-rooms");
const roomList = document.querySelector("#room-list");
const errorBox = document.querySelector("#lobby-error");
const registrationStatus = document.querySelector("#registration-status");

const STORAGE = {
  nickname: "holdem.nickname",
  guestId: "holdem.guest_id",
  registeredGuestId: "holdem.registered_guest_id",
};

nicknameInput.value = localStorage.getItem(STORAGE.nickname) || "";
renderRegistrationStatus();

createButton.addEventListener("click", () => createRoom());
joinButton.addEventListener("click", () => joinRoomFromInput());
registerButton.addEventListener("click", () => registerUser());
refreshRoomsButton.addEventListener("click", () => loadRooms());
roomCodeInput.addEventListener("input", () => {
  roomCodeInput.value = roomCodeInput.value.toUpperCase();
});
nicknameInput.addEventListener("input", () => renderRegistrationStatus());

loadRooms();
setInterval(loadRooms, 5000);

async function createRoom() {
  const nickname = requireNickname();
  if (!nickname) {
    return;
  }

  const smallBlind = Number(smallBlindInput.value || 50);
  const bigBlind = Number(bigBlindInput.value || 100);
  if (!Number.isFinite(smallBlind) || !Number.isFinite(bigBlind) || smallBlind < 1 || bigBlind < smallBlind) {
    showError("盲注设置不合法。");
    return;
  }

  await withBusy(async () => {
    const envelope = await postJson("/api/rooms", {
      nickname,
      guest_id: currentGuestId(),
      small_blind: smallBlind,
      big_blind: bigBlind,
      ai_enabled_by_default: Boolean(aiDefaultInput?.checked),
    });
    persistGuest(envelope);
    goToRoom(envelope.room.room_code, envelope.guest.guest_id);
  });
}

async function joinRoomFromInput() {
  const roomCode = roomCodeInput.value.trim().toUpperCase();
  if (!roomCode) {
    showError("请输入房间号。");
    roomCodeInput.focus();
    return;
  }
  await joinRoom(roomCode);
}

async function joinRoom(roomCode) {
  const nickname = requireNickname();
  if (!nickname) {
    return;
  }

  await withBusy(async () => {
    const envelope = await postJson(`/api/rooms/${encodeURIComponent(roomCode)}/join`, {
      nickname,
      guest_id: currentGuestId(),
    });
    persistGuest(envelope);
    goToRoom(envelope.room.room_code, envelope.guest.guest_id);
  });
}

async function registerUser() {
  const nickname = requireNickname();
  if (!nickname) {
    return;
  }

  const existingGuestId = localStorage.getItem(STORAGE.registeredGuestId);
  if (existingGuestId && localStorage.getItem(STORAGE.nickname) === nickname) {
    renderRegistrationStatus("已注册，创建或加入房间会使用这个身份。");
    return;
  }

  await withBusy(async () => {
    const guest = await postJson("/api/rooms/register", {nickname});
    localStorage.setItem(STORAGE.nickname, guest.nickname);
    localStorage.setItem(STORAGE.registeredGuestId, guest.guest_id);
    sessionStorage.setItem(STORAGE.guestId, guest.guest_id);
    nicknameInput.value = guest.nickname;
    renderRegistrationStatus("注册成功，昵称已锁定。");
  });
}

async function loadRooms() {
  try {
    const rooms = await getJson("/api/rooms");
    renderRooms(rooms);
  } catch {
    roomList.innerHTML = `<div class="empty-text">无法加载房间列表。</div>`;
  }
}

function renderRooms(rooms) {
  if (!rooms.length) {
    roomList.innerHTML = `<div class="empty-text">暂无房间，创建第一张牌桌吧。</div>`;
    return;
  }

  roomList.innerHTML = "";
  for (const room of rooms) {
    const card = document.createElement("article");
    card.className = "room-card";
    card.innerHTML = `
      <div class="section-title-row compact">
        <h3>${escapeHtml(room.room_code)}</h3>
        <span class="status-pill">${statusLabel(room.status)}</span>
      </div>
      <div class="room-meta">
        <div>房主<br><strong>${escapeHtml(room.host_nickname)}</strong></div>
        <div>座位<br><strong>${room.occupied_seats}/${room.max_seats}</strong></div>
        <div>成员<br><strong>${room.member_count}</strong></div>
        <div>盲注<br><strong>${room.small_blind}/${room.big_blind}</strong></div>
        <div>AI<br><strong>${room.ai_enabled_by_default ? "开启" : "关闭"}</strong></div>
      </div>
      <button type="button" class="secondary-button quick-join" data-room="${escapeHtml(room.room_code)}" ${room.can_join ? "" : "disabled"}>加入</button>
    `;
    roomList.appendChild(card);
  }

  for (const button of document.querySelectorAll(".quick-join")) {
    button.addEventListener("click", () => joinRoom(button.dataset.room));
  }
}

function requireNickname() {
  const nickname = nicknameInput.value.trim();
  if (!nickname) {
    showError("请输入昵称。");
    nicknameInput.focus();
    return "";
  }
  localStorage.setItem(STORAGE.nickname, nickname);
  return nickname;
}

function persistGuest(envelope) {
  localStorage.setItem(STORAGE.nickname, envelope.guest.nickname);
  if (currentGuestId() === envelope.guest.guest_id) {
    localStorage.setItem(STORAGE.registeredGuestId, envelope.guest.guest_id);
  }
  sessionStorage.setItem(STORAGE.guestId, envelope.guest.guest_id);
  sessionStorage.setItem(`holdem.room.${envelope.room.room_code}.guest_id`, envelope.guest.guest_id);
}

function goToRoom(roomCode, guestId) {
  sessionStorage.setItem(`holdem.room.${roomCode}.guest_id`, guestId);
  window.location.href = `/rooms/${encodeURIComponent(roomCode)}`;
}

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail?.message || "请求失败。");
  }
  return data;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail?.message || "请求失败。");
  }
  return data;
}

async function withBusy(task) {
  setBusy(true);
  try {
    showError("");
    await task();
  } catch (error) {
    showError(error.message || "请求失败。");
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  createButton.disabled = isBusy;
  joinButton.disabled = isBusy;
  registerButton.disabled = isBusy;
}

function showError(message) {
  errorBox.textContent = message;
}

function currentGuestId() {
  return localStorage.getItem(STORAGE.registeredGuestId) || null;
}

function renderRegistrationStatus(message = "") {
  if (message) {
    registrationStatus.textContent = message;
    return;
  }
  const registeredGuestId = localStorage.getItem(STORAGE.registeredGuestId);
  const registeredNickname = localStorage.getItem(STORAGE.nickname);
  registrationStatus.textContent = registeredGuestId && registeredNickname
    ? `已注册：${registeredNickname}`
    : "注册后可防止昵称重复。";
}

function statusLabel(status) {
  return {
    waiting: "等待中",
    playing: "游戏中",
    finished: "已结束",
  }[status] || status;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
