const roomCode = window.HOLDEM_ROOM_CODE;
const storageKeys = {
  nickname: "holdem.nickname",
  guestId: "holdem.guest_id",
  roomGuestId: `holdem.room.${roomCode}.guest_id`,
  soundEnabled: "holdem.sound.enabled",
  soundVolume: "holdem.sound.volume",
};

const params = new URLSearchParams(window.location.search);
if (params.has("new_player")) {
  sessionStorage.removeItem(storageKeys.guestId);
  sessionStorage.removeItem(storageKeys.roomGuestId);
}

let socket = null;
let state = null;
let activeGuestId = params.get("guest_id") || sessionStorage.getItem(storageKeys.roomGuestId);
let reconnectTimer = null;
let countdownTimer = null;
let heartbeatTimer = null;
const playedSoundEvents = new Set();

if (params.has("guest_id") || params.has("new_player")) {
  window.history.replaceState({}, "", `/rooms/${encodeURIComponent(roomCode)}`);
}

const elements = {
  roomHeader: document.querySelector("#room-header"),
  waitingView: document.querySelector("#waiting-view"),
  gameView: document.querySelector("#game-view"),
  connectionStatus: document.querySelector("#connection-status"),
  gameConnectionStatus: document.querySelector("#game-connection-status"),
  viewerChip: document.querySelector("#viewer-chip"),
  roomStatus: document.querySelector("#room-status"),
  revisionLabel: document.querySelector("#revision-label"),
  joinPanel: document.querySelector("#join-panel"),
  joinNickname: document.querySelector("#join-nickname"),
  joinCurrentRoom: document.querySelector("#join-current-room"),
  joinError: document.querySelector("#join-error"),
  phaseLabel: document.querySelector("#phase-label"),
  actorLabel: document.querySelector("#actor-label"),
  potTotal: document.querySelector("#pot-total"),
  currentBet: document.querySelector("#current-bet"),
  minRaise: document.querySelector("#min-raise"),
  blindLabel: document.querySelector("#blind-label"),
  communityCards: document.querySelector("#community-cards"),
  myHand: document.querySelector("#my-hand"),
  resultPanel: document.querySelector("#result-panel"),
  spectatorNote: document.querySelector("#spectator-note"),
  seatGrid: document.querySelector("#seat-grid"),
  seatCount: document.querySelector("#seat-count"),
  playersPanel: document.querySelector("#players-panel"),
  eventLog: document.querySelector("#event-log"),
  readyToggle: document.querySelector("#ready-toggle"),
  standUp: document.querySelector("#stand-up"),
  addBot: document.querySelector("#add-bot"),
  startGame: document.querySelector("#start-game"),
  tableError: document.querySelector("#table-error"),
  actionAmount: document.querySelector("#action-amount"),
  actionSlider: document.querySelector("#action-slider"),
  actionError: document.querySelector("#action-error"),
  actionButtons: Array.from(document.querySelectorAll(".action-button")),
  timeCardButton: document.querySelector("#use-time-card"),
  copyRoomLink: document.querySelector("#copy-room-link"),
  newIdentity: document.querySelector("#new-identity"),
  gameTableTitle: document.querySelector("#game-table-title"),
  gameHandPill: document.querySelector("#game-hand-pill"),
  soundToggle: document.querySelector("#sound-toggle"),
  soundVolume: document.querySelector("#sound-volume"),
  pauseGame: document.querySelector("#pause-game"),
  endGame: document.querySelector("#end-game"),
  tablePlayerPods: document.querySelector("#table-player-pods"),
  cardAnimationLayer: document.querySelector("#card-animation-layer"),
  gameActorLabel: document.querySelector("#game-actor-label"),
  gamePotTotal: document.querySelector("#game-pot-total"),
  gameCommunityCards: document.querySelector("#game-community-cards"),
  gameResultPanel: document.querySelector("#game-result-panel"),
  aiToggle: document.querySelector("#ai-toggle"),
  aiToggleLabel: document.querySelector("#ai-toggle-label"),
  aiHandLabel: document.querySelector("#ai-hand-label"),
  aiStrengthBar: document.querySelector("#ai-strength-bar"),
  aiPercentile: document.querySelector("#ai-percentile"),
  aiRank: document.querySelector("#ai-rank"),
  aiGrade: document.querySelector("#ai-grade"),
  aiWinRate: document.querySelector("#ai-win-rate"),
  aiSummary: document.querySelector("#ai-summary"),
  aiNotes: document.querySelector("#ai-notes"),
  gameStackLabel: document.querySelector("#game-stack-label"),
  amountBbLabel: document.querySelector("#amount-bb-label"),
  betRangeLabel: document.querySelector("#bet-range-label"),
  quickBets: document.querySelector("#quick-bets"),
  borrowButtons: Array.from(document.querySelectorAll(".borrow-chips")),
  chatLists: Array.from(document.querySelectorAll(".chat-list")),
  chatInputs: Array.from(document.querySelectorAll(".chat-input")),
  chatSends: Array.from(document.querySelectorAll(".chat-send")),
  showdownModal: document.querySelector("#showdown-modal"),
  showdownCommunity: document.querySelector("#showdown-community"),
  showdownTotalPot: document.querySelector("#showdown-total-pot"),
  showdownPots: document.querySelector("#showdown-pots"),
  showdownHands: document.querySelector("#showdown-hands"),
  showdownNote: document.querySelector("#showdown-note"),
  showdownReady: document.querySelector("#showdown-ready"),
  showdownNext: document.querySelector("#showdown-next"),
  showdownEnd: document.querySelector("#showdown-end"),
};

const soundManager = {
  enabled: localStorage.getItem(storageKeys.soundEnabled) !== "false",
  volume: readStoredVolume(),
  unlocked: false,
  context: null,
  unlockAudio() {
    if (!("AudioContext" in window || "webkitAudioContext" in window)) {
      return;
    }
    if (!this.context) {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      this.context = new AudioContextCtor();
    }
    this.unlocked = true;
    if (this.context.state === "suspended") {
      this.context.resume().catch(() => {});
    }
  },
  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    localStorage.setItem(storageKeys.soundEnabled, String(this.enabled));
    updateSoundUi();
  },
  setVolume(volume) {
    this.volume = clamp(Number(volume), 0, 1);
    localStorage.setItem(storageKeys.soundVolume, String(this.volume));
    updateSoundUi();
  },
  play(name, phrase = "") {
    if (!this.enabled || this.volume <= 0 || !this.unlocked) {
      return;
    }
    this.unlockAudio();
    if (phrase && this.speak(phrase)) {
      return;
    }
    if (!this.context) {
      return;
    }
    playSynthSound(this.context, name, this.volume);
  },
  speak(phrase) {
    if (!("speechSynthesis" in window) || !phrase) {
      return false;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(phrase);
    utterance.lang = "en-US";
    utterance.rate = 1.45;
    utterance.pitch = 1;
    utterance.volume = this.volume;
    window.speechSynthesis.speak(utterance);
    return true;
  },
};

elements.joinNickname.value = localStorage.getItem(storageKeys.nickname) || "";
elements.joinCurrentRoom.addEventListener("click", joinCurrentRoom);
elements.readyToggle.addEventListener("click", toggleReady);
elements.standUp.addEventListener("click", standUp);
elements.addBot.addEventListener("click", addBot);
elements.startGame.addEventListener("click", startGame);
elements.copyRoomLink.addEventListener("click", copyRoomLink);
elements.newIdentity.addEventListener("click", resetIdentity);
elements.soundToggle.addEventListener("click", toggleSound);
elements.soundVolume.addEventListener("input", () => soundManager.setVolume(elements.soundVolume.value));
elements.pauseGame.addEventListener("click", togglePauseGame);
elements.endGame.addEventListener("click", endGame);
elements.aiToggle.addEventListener("change", () => {
  if (!state?.viewer?.is_host) {
    elements.aiToggle.checked = Boolean(state?.ai_enabled_by_default);
    showActionError("只有房主可以控制 AI 助手。");
    updateAiToggleLabel();
    return;
  }
  send({type: "set_ai_enabled", payload: {is_enabled: elements.aiToggle.checked}});
});
elements.actionAmount.addEventListener("input", syncAmountUi);
elements.actionSlider.addEventListener("input", () => {
  elements.actionAmount.value = elements.actionSlider.value;
  syncAmountUi();
});
for (const button of elements.actionButtons) {
  button.addEventListener("click", () => sendPlayerAction(button.dataset.action));
}
elements.timeCardButton.addEventListener("click", useTimeCard);
for (const button of elements.borrowButtons) {
  button.addEventListener("click", borrowChips);
}
for (const button of elements.chatSends) {
  button.addEventListener("click", () => sendChatFromInput(button.closest(".chat-compose")?.querySelector(".chat-input")));
}
for (const input of elements.chatInputs) {
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendChatFromInput(input);
    }
  });
}
elements.showdownReady.addEventListener("click", () => send({type: "ready", payload: {is_ready: true}}));
elements.showdownNext.addEventListener("click", startGame);
elements.showdownEnd.addEventListener("click", endFromShowdown);
document.addEventListener("pointerdown", () => soundManager.unlockAudio(), {once: true});

updateSoundUi();
renderEmptySeats();
connect();

function connect() {
  clearTimeout(reconnectTimer);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const query = activeGuestId ? `?guest_id=${encodeURIComponent(activeGuestId)}` : "";
  socket = new WebSocket(`${protocol}://${window.location.host}/ws/rooms/${encodeURIComponent(roomCode)}${query}`);

  socket.addEventListener("open", () => {
    setConnection("已连接");
    startHeartbeat();
    if (!activeGuestId) {
      showJoinPanel(true);
    }
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "connected") {
      showJoinPanel(true);
      return;
    }
    if (message.type === "room_state") {
      const oldState = state;
      state = message.payload;
      activeGuestId = state.viewer.guest_id || activeGuestId;
      if (activeGuestId) {
        sessionStorage.setItem(storageKeys.roomGuestId, activeGuestId);
        sessionStorage.setItem(storageKeys.guestId, activeGuestId);
      }
      showJoinPanel(!activeGuestId);
      clearErrors();
      renderState();
      processRoomStateEffects(oldState, state);
      return;
    }
    if (message.type === "chat_message") {
      mergeChatMessage(message.payload);
      renderChat();
      if (message.payload?.message_id) {
        playOnce(`chat:${message.payload.room_code || roomCode}:${message.payload.message_id}`, "message");
      }
      return;
    }
    if (message.type === "action_error") {
      const messageText = message.payload?.message || "操作失败。";
      showActionError(messageText);
      showTableError(messageText);
    }
  });

  socket.addEventListener("close", () => {
    setConnection("已断开");
    stopHeartbeat();
    reconnectTimer = setTimeout(connect, 1300);
  });

  socket.addEventListener("error", () => {
    setConnection("连接错误");
  });
}

function joinCurrentRoom() {
  const nickname = elements.joinNickname.value.trim();
  if (!nickname) {
    elements.joinError.textContent = "请输入昵称。";
    elements.joinNickname.focus();
    return;
  }
  localStorage.setItem(storageKeys.nickname, nickname);
  elements.joinError.textContent = "";
  send({
    type: "join_room",
    payload: {
      room_code: roomCode,
      nickname,
      guest_id: activeGuestId || sessionStorage.getItem(storageKeys.roomGuestId),
    },
  });
}

function toggleReady() {
  if (!state) {
    return;
  }
  const mySeat = getMySeat();
  send({
    type: "ready",
    payload: {is_ready: !(mySeat?.is_ready)},
  });
}

function standUp() {
  send({type: "stand_up", payload: {}});
}

function addBot() {
  send({type: "add_bot", payload: {}});
}

function startGame() {
  send({type: "start_game", payload: {}});
}

function resetIdentity() {
  sessionStorage.removeItem(storageKeys.guestId);
  sessionStorage.removeItem(storageKeys.roomGuestId);
  window.location.href = `/rooms/${encodeURIComponent(roomCode)}?new_player=1`;
}

async function copyRoomLink() {
  const cleanUrl = `${window.location.origin}/rooms/${encodeURIComponent(roomCode)}`;
  try {
    await navigator.clipboard.writeText(cleanUrl);
    elements.copyRoomLink.textContent = "已复制";
    setTimeout(() => {
      elements.copyRoomLink.textContent = "复制链接";
    }, 1200);
  } catch {
    window.prompt("复制房间链接", cleanUrl);
  }
}

function toggleSound() {
  soundManager.unlockAudio();
  soundManager.setEnabled(!soundManager.enabled);
  if (soundManager.enabled) {
    soundManager.play("check");
  }
}

function updateSoundUi() {
  elements.soundToggle.textContent = soundManager.enabled && soundManager.volume > 0 ? "🔊" : "🔇";
  elements.soundToggle.setAttribute("aria-pressed", String(soundManager.enabled));
  elements.soundVolume.value = String(soundManager.volume);
  elements.soundVolume.disabled = !soundManager.enabled;
}

function readStoredVolume() {
  const stored = Number(localStorage.getItem(storageKeys.soundVolume));
  if (!Number.isFinite(stored)) {
    return 0.45;
  }
  return clamp(stored, 0, 1);
}

function playSynthSound(context, name, volume) {
  const presets = {
    deal: [[520, 0, 0.08], [690, 0.08, 0.09]],
    check: [[440, 0, 0.07]],
    call: [[520, 0, 0.08]],
    bet: [[560, 0, 0.08], [700, 0.07, 0.09]],
    raise: [[620, 0, 0.08], [860, 0.08, 0.11]],
    all_in: [[240, 0, 0.12], [840, 0.1, 0.18]],
    fold: [[260, 0, 0.12]],
    win: [[660, 0, 0.1], [880, 0.11, 0.12], [1180, 0.23, 0.16]],
    showdown: [[320, 0, 0.1], [480, 0.1, 0.12], [720, 0.22, 0.14]],
    message: [[760, 0, 0.05]],
  };
  const tones = presets[name] || presets.check;
  const baseTime = context.currentTime;
  for (const [frequency, delay, duration] of tones) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = name === "fold" ? "triangle" : "sine";
    oscillator.frequency.setValueAtTime(frequency, baseTime + delay);
    gain.gain.setValueAtTime(0.0001, baseTime + delay);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, volume * 0.12), baseTime + delay + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, baseTime + delay + duration);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(baseTime + delay);
    oscillator.stop(baseTime + delay + duration + 0.02);
  }
}

function togglePauseGame() {
  if (!state?.viewer?.is_host) {
    showActionError("只有房主可以暂停或继续牌局。");
    return;
  }
  send({
    type: "pause_game",
    payload: {is_paused: !Boolean(state.is_paused)},
  });
}

function endGame() {
  if (!state?.viewer?.is_host) {
    showActionError("只有房主可以结束当前牌局。");
    return;
  }
  if (window.confirm("确定结束当前牌局吗？本局已投入筹码会退回，房间回到等待状态。")) {
    send({type: "end_game", payload: {}});
  }
}

function endFromShowdown() {
  if (state?.status === "playing") {
    endGame();
    return;
  }
  window.location.href = "/";
}

function borrowChips() {
  if (!canBorrowChips()) {
    showActionError("只有坐下且输光、并且不在当前手牌中的玩家可以领取训练筹码。");
    showTableError("只有坐下且输光、并且不在当前手牌中的玩家可以领取训练筹码。");
    return;
  }
  send({type: "claim_training_chips", payload: {amount: 5000}});
}

function sendChatFromInput(input) {
  if (!input) {
    return;
  }
  const content = input.value.trim();
  if (!content) {
    return;
  }
  if (content.length > 200) {
    showActionError("聊天内容不能超过 200 字。");
    return;
  }
  send({type: "send_chat_message", payload: {content}});
  for (const item of elements.chatInputs) {
    item.value = "";
  }
}

function sendPlayerAction(action) {
  const payload = {action};
  if (action === "bet" || action === "raise") {
    const amount = Number(elements.actionAmount.value);
    if (!Number.isFinite(amount) || amount <= 0) {
      showActionError("请输入下注或加注目标额。");
      elements.actionAmount.focus();
      return;
    }
    payload.amount = amount;
  }
  send({type: "player_action", payload});
}

function useTimeCard() {
  if (!state?.viewer?.can_act) {
    showActionError("只有轮到你行动时可以使用时间卡。");
    return;
  }
  const mySeat = getMySeat();
  if (!mySeat || Number(mySeat.time_cards_remaining || 0) <= 0) {
    showActionError("时间卡已经用完。");
    return;
  }
  send({type: "use_time_card", payload: {}});
}

function send(message) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    showActionError("WebSocket 未连接。");
    return;
  }
  soundManager.unlockAudio();
  socket.send(JSON.stringify({
    request_id: makeRequestId(),
    ...message,
  }));
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(sendHeartbeat, 1000);
  sendHeartbeat();
}

function stopHeartbeat() {
  clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

function sendHeartbeat() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(JSON.stringify({
    type: "heartbeat",
    request_id: makeRequestId(),
    payload: {},
  }));
}

function makeRequestId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function renderState() {
  const isGameMode = state.status === "playing" || Boolean(state.last_result);
  elements.roomHeader.classList.toggle("hidden", isGameMode);
  elements.waitingView.classList.toggle("hidden", isGameMode);
  elements.gameView.classList.toggle("hidden", !isGameMode);

  if (isGameMode) {
    renderGameView();
  } else {
    renderWaitingView();
  }
  setViewerChip();
  renderBorrowControls();
  renderChat();
}

function processRoomStateEffects(oldState, newState) {
  if (!oldState || oldState.room_code !== newState.room_code) {
    return;
  }
  playActionTransitionSounds(oldState, newState);
  playResultTransitionSounds(oldState, newState);

  const sameHand = oldState.hand_number === newState.hand_number;
  if (newState.status === "playing" && oldState.hand_number !== newState.hand_number && newState.hand_number > 0) {
    animateHoleCards(newState);
    return;
  }
  if (sameHand) {
    animateCommunityTransitions(oldState, newState);
  }
}

function animateHoleCards(roomState) {
  const seats = dealOrder(roomState);
  if (!seats.length || prefersReducedMotion()) {
    playOnce(`deal:hole:${roomState.hand_number}`, "deal", "Deal");
    return;
  }
  playOnce(`deal:hole:${roomState.hand_number}`, "deal", "Deal");
  let delay = 0;
  for (let round = 0; round < 2; round += 1) {
    for (const seat of seats) {
      const target = targetForSeatCard(seat.seat_index, round);
      const card = visibleAnimationCard(seat.hole_cards?.[round]);
      animateCardToTarget(card, target, delay);
      delay += 95;
    }
  }
}

function animateCommunityTransitions(oldState, newState) {
  const oldCount = (oldState.community_cards || []).length;
  const newCount = (newState.community_cards || []).length;
  if (newCount <= oldCount) {
    return;
  }

  const ranges = [];
  if (oldCount < 3 && newCount >= 3) {
    ranges.push([0, 3]);
  }
  if (oldCount < 4 && newCount >= 4) {
    ranges.push([3, 4]);
  }
  if (oldCount < 5 && newCount >= 5) {
    ranges.push([4, 5]);
  }
  if (!ranges.length) {
    return;
  }
  playOnce(
    `deal:board:${newState.hand_number}:${oldCount}->${newCount}`,
    "deal",
    boardVoiceLabel(oldCount, newCount),
  );
  if (prefersReducedMotion()) {
    return;
  }

  let delay = 0;
  for (const [start, end] of ranges) {
    for (let index = start; index < end; index += 1) {
      const target = elements.gameCommunityCards.children[index];
      animateCardToTarget(newState.community_cards[index], target, delay);
      delay += 115;
    }
  }
}

function boardVoiceLabel(oldCount, newCount) {
  if (oldCount < 3 && newCount >= 3) {
    return "Flop";
  }
  if (oldCount < 4 && newCount >= 4) {
    return "Turn";
  }
  if (oldCount < 5 && newCount >= 5) {
    return "River";
  }
  return "Deal";
}

function animateCardToTarget(card, target, delay) {
  if (!elements.cardAnimationLayer || !target) {
    return;
  }
  const layer = elements.cardAnimationLayer;
  const feltRect = layer.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  if (!feltRect.width || !feltRect.height || !targetRect.width || !targetRect.height) {
    return;
  }

  const animatedCard = renderCard(card || "hidden");
  animatedCard.classList.add("flying-card");
  const cardWidth = 54;
  const cardHeight = 76;
  const startX = feltRect.width / 2 - cardWidth / 2;
  const startY = feltRect.height * 0.42 - cardHeight / 2;
  const targetX = targetRect.left - feltRect.left + targetRect.width / 2 - cardWidth / 2;
  const targetY = targetRect.top - feltRect.top + targetRect.height / 2 - cardHeight / 2;
  animatedCard.style.left = `${startX}px`;
  animatedCard.style.top = `${startY}px`;
  animatedCard.style.setProperty("--card-dx", `${targetX - startX}px`);
  animatedCard.style.setProperty("--card-dy", `${targetY - startY}px`);
  animatedCard.style.setProperty("--card-rot", `${Math.random() > 0.5 ? 7 : -7}deg`);
  layer.appendChild(animatedCard);

  window.setTimeout(() => {
    window.requestAnimationFrame(() => animatedCard.classList.add("in-flight"));
  }, delay);
  window.setTimeout(() => {
    animatedCard.classList.add("leaving");
    window.setTimeout(() => animatedCard.remove(), 180);
  }, delay + 640);
}

function dealOrder(roomState) {
  const maxSeats = roomState.seats?.length || 20;
  const buttonIndex = roomState.button_seat_index ?? 0;
  return (roomState.seats || [])
    .filter((seat) => seat.occupied && isSeatInDealtHand(seat))
    .sort((left, right) => {
      const leftOffset = (left.seat_index - buttonIndex - 1 + maxSeats) % maxSeats;
      const rightOffset = (right.seat_index - buttonIndex - 1 + maxSeats) % maxSeats;
      return leftOffset - rightOffset;
    });
}

function isSeatInDealtHand(seat) {
  return Boolean(
    seat.hole_cards?.length ||
    seat.current_bet ||
    seat.total_committed ||
    seat.position_label ||
    seat.has_folded ||
    seat.is_all_in
  );
}

function targetForSeatCard(seatIndex, round) {
  const pod = elements.tablePlayerPods.querySelector(`[data-seat-index="${seatIndex}"]`);
  return pod?.querySelector(`.mini-card:nth-child(${round + 1})`) || pod;
}

function visibleAnimationCard(card) {
  return card && card !== "hidden" ? card : "hidden";
}

function prefersReducedMotion() {
  if (typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function playActionTransitionSounds(oldState, newState) {
  const oldSeats = new Map((oldState.seats || []).map((seat) => [seat.seat_index, seat]));
  for (const seat of newState.seats || []) {
    if (!seat.occupied) {
      continue;
    }
    const oldSeat = oldSeats.get(seat.seat_index);
    if (!oldSeat || !seat.last_action) {
      continue;
    }
    const changed = oldSeat.last_action !== seat.last_action ||
      oldSeat.current_bet !== seat.current_bet ||
      oldSeat.total_committed !== seat.total_committed ||
      oldSeat.has_folded !== seat.has_folded ||
      oldSeat.is_all_in !== seat.is_all_in;
    if (!changed) {
      continue;
    }
    const soundName = soundForSeatAction(oldSeat, seat);
    const key = [
      "action",
      newState.hand_number,
      seat.seat_index,
      seat.last_action,
      seat.current_bet,
      seat.total_committed,
      seat.chips,
      seat.has_folded,
      seat.is_all_in,
    ].join(":");
    playOnce(key, soundName, voiceTextForSeatAction(oldSeat, seat));
  }
}

function voiceTextForSeatAction(oldSeat, seat) {
  const action = seat.last_action || "";

  if (action === "fold") {
    return "Fold";
  }
  if (action === "check") {
    return "Check";
  }
  if (action === "call") {
    return "Call";
  }
  if (action === "bet") {
    return "Bet";
  }
  if (action === "raise") {
    return "Raise";
  }
  if (action === "all_in" || (!oldSeat.is_all_in && seat.is_all_in)) {
    return "All in";
  }
  return "";
}

function soundForSeatAction(oldSeat, seat) {
  if (seat.last_action === "all_in" || (!oldSeat.is_all_in && seat.is_all_in)) {
    return "all_in";
  }
  if (seat.last_action === "fold" || (!oldSeat.has_folded && seat.has_folded)) {
    return "fold";
  }
  if (seat.last_action === "raise") {
    return "raise";
  }
  if (seat.last_action === "bet") {
    return "bet";
  }
  if (seat.last_action === "call") {
    return "call";
  }
  return "check";
}

function playResultTransitionSounds(oldState, newState) {
  if (oldState.last_result || !newState.last_result) {
    return;
  }
  const showdownHands = newState.last_result.showdown_hands || [];
  playOnce(
    `result:showdown:${newState.hand_number}:${newState.revision}`,
    showdownHands.length ? "showdown" : "win",
    showdownHands.length ? "Showdown" : "",
  );
  window.setTimeout(() => {
    playOnce(`result:win:${newState.hand_number}:${newState.revision}`, "win");
  }, 260);
}

function playOnce(key, soundName, phrase = "") {
  if (!key || playedSoundEvents.has(key)) {
    return;
  }
  playedSoundEvents.add(key);
  if (playedSoundEvents.size > 300) {
    const staleKeys = Array.from(playedSoundEvents).slice(0, 80);
    for (const staleKey of staleKeys) {
      playedSoundEvents.delete(staleKey);
    }
  }
  soundManager.play(soundName, phrase);
}

function renderWaitingView() {
  elements.phaseLabel.textContent = phaseLabel(state.phase);
  elements.roomStatus.textContent = statusLabel(state.status);
  elements.revisionLabel.textContent = `版本 ${state.revision}`;
  elements.potTotal.textContent = formatChips(state.pot_total);
  elements.currentBet.textContent = formatChips(state.current_bet);
  elements.minRaise.textContent = formatChips(state.min_raise);
  elements.blindLabel.textContent = `${formatChips(state.small_blind)} / ${formatChips(state.big_blind)}`;

  const actorSeat = getSeatByIndex(state.current_actor_seat_index);
  elements.actorLabel.textContent = actorSeat?.nickname
    ? `行动中：${actorSeat.nickname} / ${actorSeat.seat_index + 1} 号座位`
    : "等待玩家准备";

  const occupiedCount = state.seats.filter((seat) => seat.occupied).length;
  elements.seatCount.textContent = `${occupiedCount} / ${state.seats.length}`;

  renderCards(elements.communityCards, state.community_cards, {emptyText: "公共牌会显示在这里"});
  renderWaitingHand();
  renderSeats();
  renderPlayers();
  renderWaitingControls();
  renderResult(elements.resultPanel);
  renderEvents();
  renderShowdownModal();
}

function renderGameView() {
  elements.gameView.classList.toggle("paused", Boolean(state.is_paused));
  elements.gameTableTitle.textContent = `${state.player_count || activeSeats().length}人桌`;
  elements.gameHandPill.textContent = `手牌 #${state.hand_number || 0}`;
  elements.gamePotTotal.textContent = `底池: ${formatChips(state.pot_total)}`;
  elements.pauseGame.textContent = state.is_paused ? "继续" : "暂停";
  elements.pauseGame.disabled = !state.viewer.is_host || state.status !== "playing";
  elements.endGame.disabled = !state.viewer.is_host || state.status !== "playing";

  const actorSeat = getSeatByIndex(state.current_actor_seat_index);
  elements.gameActorLabel.textContent = state.is_paused
    ? "牌局已暂停"
    : state.last_result
    ? "本手牌结束"
    : actorSeat?.nickname
    ? `行动中：${actorSeat.nickname}`
    : "等待服务端推进";

  renderBoardCards();
  renderPlayerPods();
  renderAiAssistant();
  renderBetPanel();
  renderResult(elements.gameResultPanel);
  renderShowdownModal();
  startCountdown();
}

function renderWaitingHand() {
  const mySeat = getMySeat();
  renderCards(elements.myHand, mySeat?.hole_cards || [], {emptyText: "暂无手牌"});
  elements.spectatorNote.textContent = mySeat
    ? mySeat.is_ready ? "你已准备，等待下一局开始。" : "准备后即可参与下一局。"
    : "旁观者可以看牌桌状态，但不能操作。";
}

function renderSeats() {
  elements.seatGrid.innerHTML = "";
  for (const seat of state.seats) {
    const card = document.createElement("article");
    const isMine = seat.guest_id && seat.guest_id === activeGuestId;
    card.className = [
      "seat-card",
      isMine ? "mine" : "",
      seat.is_current_actor ? "acting" : "",
    ].join(" ");

    if (!seat.occupied) {
      card.innerHTML = `
        <div class="seat-top">
          <div>
            <div class="seat-name">${seat.seat_index + 1} 号座位</div>
            <div class="seat-sub">空位</div>
          </div>
        </div>
        <button class="secondary-button sit-button" data-seat="${seat.seat_index}">坐下</button>
      `;
    } else {
      const badges = [
        seat.position_label || "",
        seat.is_bot ? "机器人" : "",
        seat.is_ready ? "已准备" : "",
        seat.has_folded ? "已弃牌" : "",
        seat.is_all_in ? "全下" : "",
        seat.is_current_actor ? "行动中" : "",
        seat.is_connected ? "" : "离线",
      ].filter(Boolean);
      card.innerHTML = `
        <div class="seat-top">
          <div class="min-w-0">
            <div class="seat-name">${escapeHtml(seat.nickname || "玩家")}</div>
            <div class="seat-sub">${seat.seat_index + 1} 号座位${isMine ? " / 你" : ""}</div>
          </div>
          <div class="seat-sub">${actionLabel(seat.last_action || "")}</div>
        </div>
        <div class="seat-stats">
          <div>筹码<br><strong>${formatChips(seat.chips)}</strong></div>
          <div>下注<br><strong>${formatChips(seat.current_bet)}</strong></div>
        </div>
        ${seat.training_chips_awarded ? `<div class="seat-debt">训练奖励：${formatChips(seat.training_chips_awarded)}</div>` : ""}
        <div class="badge-row">${badges.map((badge) => `<span class="status-pill">${badge}</span>`).join("")}</div>
      `;
    }
    elements.seatGrid.appendChild(card);
  }

  for (const button of document.querySelectorAll(".sit-button")) {
    button.disabled = !activeGuestId;
    button.addEventListener("click", () => {
      send({
        type: "sit_down",
        payload: {seat_index: Number(button.dataset.seat)},
      });
    });
  }
}

function renderPlayerPods() {
  const seats = activeSeats();
  elements.tablePlayerPods.innerHTML = "";
  if (!seats.length) {
    return;
  }

  const ordered = displaySeatOrder(seats);
  const opponents = ordered.filter((seat) => seat.guest_id !== activeGuestId);
  let opponentIndex = 0;
  for (const [index, seat] of ordered.entries()) {
    const isMine = seat.guest_id === activeGuestId;
    const point = isMine
      ? seatPoint(index, ordered.length, true)
      : seatPoint(opponentIndex++, opponents.length, false);
    const pod = document.createElement("article");
    pod.className = [
      "player-pod",
      isMine ? "hero-pod" : "",
      seat.has_folded ? "folded" : "",
      seat.is_current_actor ? "is-acting" : "",
    ].join(" ");
    pod.dataset.seatIndex = String(seat.seat_index);
    pod.style.setProperty("--seat-x", `${point.x}%`);
    pod.style.setProperty("--seat-y", `${point.y}%`);

    const cardMarkup = miniCardMarkup(seat.hole_cards || []);
    const badges = [
      seat.position_label ? `<span class="pod-position">${seat.position_label}</span>` : "",
      seat.has_folded ? `<span class="pod-folded">弃牌</span>` : "",
      seat.is_all_in ? `<span class="pod-folded">全下</span>` : "",
      seat.last_action ? `<span class="pod-action">${actionLabel(seat.last_action)}</span>` : "",
      seat.is_current_actor ? `<span class="pod-action">时间卡 ${Number(seat.time_cards_remaining || 0)}</span>` : "",
    ].filter(Boolean).join("");

    pod.innerHTML = `
      <div class="pod-top">
        <div class="pod-name">${escapeHtml(seat.nickname || "玩家")}</div>
        ${seat.is_bot ? `<span class="pod-bot">AI</span>` : ""}
        <div class="mini-cards">${cardMarkup}</div>
      </div>
      <div class="pod-bottom">
        <div class="pod-badges">${badges}</div>
        <div class="pod-stack">
          <div class="pod-chips">${formatChips(seat.chips)}</div>
          ${seat.training_chips_awarded ? `<div class="pod-debt">奖励 ${formatChips(seat.training_chips_awarded)}</div>` : ""}
        </div>
      </div>
      ${seat.current_bet ? `<div class="seat-bet-chip">${formatChips(seat.current_bet)}</div>` : ""}
      ${seat.is_current_actor ? `<div class="countdown" data-countdown>--s</div>` : ""}
    `;
    elements.tablePlayerPods.appendChild(pod);
  }
}

function renderBoardCards() {
  elements.gameCommunityCards.innerHTML = "";
  for (let index = 0; index < 5; index += 1) {
    const card = state.community_cards[index];
    if (card) {
      elements.gameCommunityCards.appendChild(renderCard(card));
    } else {
      const slot = document.createElement("div");
      slot.className = "board-slot";
      elements.gameCommunityCards.appendChild(slot);
    }
  }
}

function updateAiToggleLabel() {
  elements.aiToggleLabel.textContent = elements.aiToggle.checked ? "开启" : "关闭";
}

function renderAiAssistant() {
  const ai = state.ai_assistant || {};
  const roomAiEnabled = Boolean(state.ai_enabled_by_default);
  elements.aiToggle.checked = roomAiEnabled;
  elements.aiToggle.disabled = !state.viewer.is_host;
  const enabled = roomAiEnabled && ai.enabled;
  updateAiToggleLabel();
  elements.aiHandLabel.textContent = enabled ? ai.hand_label : "AI 助手未开启";
  elements.aiStrengthBar.style.width = `${enabled ? ai.strength_percent || 0 : 0}%`;
  elements.aiPercentile.textContent = enabled ? ai.percentile_label || "Top --" : "Top --";
  elements.aiRank.textContent = enabled ? ai.rank_text || "--" : "--";
  elements.aiGrade.textContent = enabled ? ai.grade || "--" : "--";
  elements.aiWinRate.textContent = enabled ? `${Number(ai.win_rate_percent || 0).toFixed(1)}%` : "--%";
  elements.aiSummary.textContent = enabled
    ? ai.summary || "等待更多牌局信息。"
    : "开启后会显示当前手牌强度、胜率估算和行动建议。";
  elements.aiNotes.innerHTML = "";
  const notes = enabled ? ai.draw_notes || [] : [];
  if (!notes.length) {
    elements.aiNotes.textContent = "暂无分析。";
    return;
  }
  for (const note of notes) {
    const item = document.createElement("div");
    item.textContent = note;
    elements.aiNotes.appendChild(item);
  }
}

function renderBetPanel() {
  const mySeat = getMySeat();
  const options = state.action_options || {};
  const legal = new Set(state.viewer.legal_actions);
  const minTarget = options.min_raise_to ?? options.min_bet ?? 0;
  const maxTarget = options.max_raise_to ?? options.max_bet ?? 0;
  const controlsEnabled = state.viewer.can_act && !state.is_paused;
  const canChooseAmount = controlsEnabled && Boolean(minTarget && maxTarget);
  const timeCardsRemaining = Number(mySeat?.time_cards_remaining || 0);

  elements.gameStackLabel.textContent = `有效筹码: ${formatChips(mySeat?.chips || 0)}`;
  elements.timeCardButton.textContent = `时间卡 +30s（剩余 ${timeCardsRemaining}）`;
  elements.timeCardButton.disabled = !controlsEnabled || timeCardsRemaining <= 0;
  elements.betRangeLabel.textContent = minTarget && maxTarget
    ? `范围: ${formatChips(minTarget)} - ${formatChips(maxTarget)}`
    : "范围: 无可用下注";

  elements.actionAmount.disabled = !canChooseAmount;
  elements.actionSlider.disabled = !canChooseAmount;
  elements.actionSlider.min = String(minTarget || 0);
  elements.actionSlider.max = String(maxTarget || 0);
  if (!elements.actionAmount.value && minTarget) {
    elements.actionAmount.value = String(minTarget);
  }
  if (minTarget && maxTarget) {
    const currentValue = clamp(Number(elements.actionAmount.value || minTarget), minTarget, maxTarget);
    elements.actionAmount.value = String(currentValue);
    elements.actionSlider.value = String(currentValue);
  }

  renderQuickBets(canChooseAmount ? options.quick_bets || {} : {});
  updateActionButtons(legal, options);
  syncAmountUi();
}

function renderQuickBets(quickBets) {
  elements.quickBets.innerHTML = "";
  const entries = Object.entries(quickBets);
  if (!entries.length) {
    for (const label of ["最小", "3BB", "4BB", "5BB", "全下"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.disabled = true;
      elements.quickBets.appendChild(button);
    }
    return;
  }
  for (const [label, amount] of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => {
      elements.actionAmount.value = String(amount);
      elements.actionSlider.value = String(amount);
      syncAmountUi();
    });
    elements.quickBets.appendChild(button);
  }
}

function updateActionButtons(legal, options) {
  for (const button of elements.actionButtons) {
    const action = button.dataset.action;
    button.disabled = !state.viewer.can_act || state.is_paused || !legal.has(action);
    if (action === "call") {
      button.textContent = `跟注 ${formatChips(options.to_call || 0)}`;
    } else if (action === "bet") {
      const amount = Number(elements.actionAmount.value || options.min_bet || 0);
      button.textContent = `下注 ${formatChips(amount)}`;
    } else if (action === "raise") {
      const amount = Number(elements.actionAmount.value || options.min_raise_to || 0);
      button.textContent = `加注 ${formatChips(amount)}`;
    } else if (action === "all_in") {
      button.textContent = `全下 ${formatChips(options.all_in_amount || 0)}`;
    } else {
      button.textContent = actionLabel(action);
    }
  }
}

function renderPlayers() {
  const players = state.seats.filter((seat) => seat.occupied);
  if (!players.length) {
    elements.playersPanel.innerHTML = `<div class="empty-text">暂无入座玩家。</div>`;
    return;
  }
  elements.playersPanel.innerHTML = "";
  for (const player of players) {
    const row = document.createElement("div");
    row.className = "player-row";
    row.innerHTML = `
      <span>${escapeHtml(player.nickname || "玩家")} <span class="muted-text">${player.seat_index + 1} 号${player.is_bot ? " / 机器人" : ""}${player.training_chips_awarded ? ` / 训练奖励 ${formatChips(player.training_chips_awarded)}` : ""}</span></span>
      <strong>${formatChips(player.chips)}</strong>
    `;
    elements.playersPanel.appendChild(row);
  }
}

function renderEvents() {
  const events = state.event_log || [];
  if (!events.length) {
    elements.eventLog.innerHTML = `<div class="empty-text">牌桌事件会显示在这里。</div>`;
    return;
  }
  elements.eventLog.innerHTML = "";
  for (const event of events.slice(-35)) {
    const row = document.createElement("div");
    row.className = "event-row";
    row.innerHTML = `
      <time>${formatTime(event.created_at)} / ${eventLabel(event.type)}</time>
      <div>${escapeHtml(event.message)}</div>
    `;
    elements.eventLog.appendChild(row);
  }
}

function renderEmptySeats() {
  elements.seatGrid.innerHTML = "";
  for (let index = 0; index < 20; index += 1) {
    const card = document.createElement("article");
    card.className = "seat-card";
    card.innerHTML = `<div class="seat-name">${index + 1} 号座位</div><div class="seat-sub">等待</div>`;
    elements.seatGrid.appendChild(card);
  }
}

function renderWaitingControls() {
  const mySeat = getMySeat();
  const isJoined = Boolean(activeGuestId);
  const isSitting = Boolean(mySeat);
  const isPlaying = state.status === "playing";

  elements.readyToggle.disabled = !isJoined || !isSitting || isPlaying;
  elements.readyToggle.textContent = mySeat?.is_ready ? "取消准备" : "准备";
  elements.standUp.disabled = !isJoined || !isSitting || isPlaying;
  elements.addBot.disabled = !state.viewer.is_host || isPlaying;
  elements.startGame.disabled = !state.viewer.is_host || isPlaying;
}

function renderBorrowControls() {
  const canBorrow = canBorrowChips();
  for (const button of elements.borrowButtons) {
    button.classList.toggle("hidden", !canBorrow);
    button.disabled = !canBorrow;
  }
}

function canBorrowChips() {
  const mySeat = getMySeat();
  if (!mySeat || mySeat.chips !== 0) {
    return false;
  }
  return !isSeatInActiveHand(mySeat);
}

function isSeatInActiveHand(seat) {
  if (!seat || state.status !== "playing") {
    return false;
  }
  return Boolean(
    seat.is_current_actor ||
    seat.has_folded ||
    seat.is_all_in ||
    seat.current_bet ||
    seat.total_committed ||
    (seat.hole_cards && seat.hole_cards.length > 0)
  );
}

function renderChat() {
  const messages = state?.chat_messages || [];
  for (const list of elements.chatLists) {
    list.innerHTML = "";
    if (!messages.length) {
      list.innerHTML = `<div class="empty-text">暂无聊天消息。</div>`;
      continue;
    }
    for (const message of messages.slice(-100)) {
      const row = document.createElement("div");
      row.className = [
        "chat-message",
        message.is_system ? "system" : "",
        message.guest_id && message.guest_id === activeGuestId ? "mine" : "",
      ].join(" ");
      row.innerHTML = `
        <div class="chat-meta">
          <span>${escapeHtml(message.nickname || "玩家")}</span>
          <time>${formatTime(message.created_at)}</time>
        </div>
        <div class="chat-bubble">${escapeHtml(message.content || "")}</div>
      `;
      list.appendChild(row);
    }
    list.scrollTop = list.scrollHeight;
  }
}

function mergeChatMessage(message) {
  if (!message) {
    return;
  }
  if (!state) {
    state = {chat_messages: [message]};
    return;
  }
  const messages = state.chat_messages || [];
  if (!messages.some((item) => item.message_id === message.message_id)) {
    state.chat_messages = [...messages, message].slice(-100);
  }
}

function renderShowdownModal() {
  if (!elements.showdownModal) {
    return;
  }
  const result = state?.last_result;
  elements.showdownModal.classList.toggle("hidden", !result);
  if (!result) {
    return;
  }

  renderCards(elements.showdownCommunity, state.community_cards || [], {emptyText: "无公共牌"});
  elements.showdownTotalPot.textContent = `$${formatChips(totalResultPot(result))}`;
  renderShowdownPots(result);
  renderShowdownHands(result);

  const mySeat = getMySeat();
  const readyBreakReady = isReadyBreakReadyToStart();
  elements.showdownNote.textContent = state.ready_break_required
    ? "已完成 20 手，请重新准备后继续。"
    : "慢慢看，准备好了就开始下一手";
  elements.showdownReady.classList.toggle("hidden", !state.ready_break_required || !mySeat);
  elements.showdownReady.disabled = !mySeat || mySeat.is_ready;
  elements.showdownReady.textContent = mySeat?.is_ready ? "已准备" : "准备";
  elements.showdownNext.disabled = !state.viewer.is_host || (state.ready_break_required && !readyBreakReady);
  elements.showdownNext.textContent = state.ready_break_required ? "▶ 下一阶段" : "▶ 下一手";
}

function renderShowdownPots(result) {
  elements.showdownPots.innerHTML = "";
  const distributions = result.pot_distributions || [];
  if (!distributions.length) {
    elements.showdownPots.innerHTML = `<div class="empty-text">暂无底池分配。</div>`;
    return;
  }
  for (const pot of distributions) {
    const card = document.createElement("article");
    card.className = "showdown-pot-card";
    const winners = (pot.shares || []).map((share) => {
      const seat = getSeatByIndex(share.seat_index);
      const winner = (result.winners || []).find((item) => item.seat_index === share.seat_index);
      const handLabel = winner?.hand_category_name ? handNameLabel(winner.hand_category_name) : "胜出";
      return `
        <div class="showdown-pot-row">
          <span>♛ ${escapeHtml(seat?.nickname || `${share.seat_index + 1} 号座位`)}</span>
          <strong>${handLabel} / +${formatChips(share.amount)}</strong>
        </div>
      `;
    }).join("");
    card.innerHTML = `
      <div class="showdown-pot-heading">
        <span>${pot.pot_index === 0 ? "主池" : `边池 ${pot.pot_index}`}</span>
        <strong>$${formatChips(pot.amount)}</strong>
      </div>
      ${winners}
    `;
    elements.showdownPots.appendChild(card);
  }
}

function renderShowdownHands(result) {
  elements.showdownHands.innerHTML = "";
  const showdownBySeat = new Map((result.showdown_hands || []).map((hand) => [hand.seat_index, hand]));
  const winnerSeats = new Set((result.winners || []).map((winner) => winner.seat_index));
  const seats = activeSeats().filter((seat) => {
    return winnerSeats.has(seat.seat_index) || showdownBySeat.has(seat.seat_index) || (seat.hole_cards || []).length;
  });
  if (!seats.length) {
    elements.showdownHands.innerHTML = `<div class="empty-text">无人摊牌，只剩一名玩家未弃牌。</div>`;
    return;
  }
  for (const seat of seats) {
    const hand = showdownBySeat.get(seat.seat_index);
    const winner = (result.winners || []).find((item) => item.seat_index === seat.seat_index);
    const card = document.createElement("article");
    card.className = `showdown-hand-card ${winner ? "winner" : ""}`;
    card.innerHTML = `
      <div>
        <strong>${winner ? "♛ " : ""}${escapeHtml(seat.nickname || "玩家")}</strong>
        <span>${hand ? handNameLabel(hand.category_name) : winner ? "弃牌胜出" : seat.has_folded ? "已弃牌" : "未摊牌"}</span>
      </div>
      <div class="showdown-hole-cards">${miniCardMarkup(seat.hole_cards || [])}</div>
    `;
    elements.showdownHands.appendChild(card);
  }
}

function totalResultPot(result) {
  return (result.pot_distributions || []).reduce((total, pot) => total + (pot.amount || 0), 0);
}

function isReadyBreakReadyToStart() {
  if (!state.ready_break_required) {
    return true;
  }
  const eligible = activeSeats().filter((seat) => seat.chips > 0);
  return eligible.length >= 2 && eligible.every((seat) => seat.is_ready);
}

function renderResult(container) {
  container.innerHTML = "";
  if (!state.last_result || !state.last_result.winners.length) {
    return;
  }
  for (const winner of state.last_result.winners) {
    const pill = document.createElement("div");
    pill.className = "result-pill";
    pill.textContent = `${winner.seat_index + 1} 号座位赢得 ${formatChips(winner.amount)}${winner.hand_category_name ? ` / ${handNameLabel(winner.hand_category_name)}` : ""}`;
    container.appendChild(pill);
  }
}

function renderCards(container, cards, {emptyText}) {
  container.innerHTML = "";
  if (!cards || cards.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-text";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  for (const card of cards) {
    container.appendChild(renderCard(card));
  }
}

function renderCard(card) {
  const el = document.createElement("div");
  if (card === "hidden") {
    el.className = "playing-card hidden-card";
    return el;
  }
  const {rank, symbol, red} = parseCard(card);
  el.className = `playing-card ${red ? "red" : ""}`;
  el.textContent = `${rank}${symbol}`;
  return el;
}

function miniCardMarkup(cards) {
  if (!cards || !cards.length) {
    return `<span class="mini-card card-back"></span><span class="mini-card card-back"></span>`;
  }
  return cards.map((card) => {
    if (card === "hidden") {
      return `<span class="mini-card card-back"></span>`;
    }
    const {rank, symbol, red} = parseCard(card);
    return `<span class="mini-card ${red ? "red" : ""}">${rank}${symbol}</span>`;
  }).join("");
}

function setConnection(label) {
  elements.connectionStatus.textContent = label;
  elements.gameConnectionStatus.innerHTML = `<i></i> ${label}`;
}

function setViewerChip() {
  const mySeat = getMySeat();
  elements.viewerChip.textContent = mySeat
    ? `${mySeat.seat_index + 1} 号座位 / ${formatChips(mySeat.chips)}`
    : activeGuestId ? "旁观" : "未进入";
}

function showJoinPanel(show) {
  elements.joinPanel.classList.toggle("hidden", !show);
}

function clearErrors() {
  elements.actionError.textContent = "";
  elements.tableError.textContent = "";
}

function showActionError(message) {
  elements.actionError.textContent = message;
}

function showTableError(message) {
  elements.tableError.textContent = message;
}

function syncAmountUi() {
  const value = Number(elements.actionAmount.value || 0);
  elements.amountBbLabel.textContent = `(${(value / Math.max(1, state?.big_blind || 1)).toFixed(1)} BB)`;
  if (state) {
    updateActionButtons(new Set(state.viewer.legal_actions), state.action_options || {});
  }
}

function startCountdown() {
  clearInterval(countdownTimer);
  updateCountdown();
  countdownTimer = setInterval(updateCountdown, 250);
}

function updateCountdown() {
  const nodes = document.querySelectorAll("[data-countdown]");
  if (!nodes.length) {
    return;
  }
  if (state?.is_paused) {
    for (const node of nodes) {
      node.textContent = "暂停";
    }
    return;
  }
  const expiresAt = state?.action_expires_at ? new Date(state.action_expires_at).getTime() : 0;
  const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
  for (const node of nodes) {
    node.textContent = `${remaining}s`;
  }
}

function activeSeats() {
  return state.seats.filter((seat) => seat.occupied);
}

function displaySeatOrder(seats) {
  const mySeat = getMySeat();
  if (!mySeat) {
    return [...seats].sort((left, right) => left.seat_index - right.seat_index);
  }
  return [...seats].sort((left, right) => {
    const leftOffset = (left.seat_index - mySeat.seat_index + state.seats.length) % state.seats.length;
    const rightOffset = (right.seat_index - mySeat.seat_index + state.seats.length) % state.seats.length;
    return leftOffset - rightOffset;
  });
}

function seatPoint(index, count, isMine) {
  if (isMine) {
    return {x: 50, y: 86};
  }
  const fixedByCount = {
    1: [{x: 50, y: 17}],
    2: [{x: 28, y: 23}, {x: 72, y: 23}],
    3: [{x: 50, y: 16}, {x: 20, y: 44}, {x: 80, y: 44}],
    4: [{x: 30, y: 18}, {x: 70, y: 18}, {x: 18, y: 52}, {x: 82, y: 52}],
  };
  if (fixedByCount[count]?.[index]) {
    return fixedByCount[count][index];
  }
  const narrow = window.innerWidth <= 680;
  const radiusX = narrow ? 28 : 38;
  const radiusY = narrow ? 30 : 35;
  const angle = (90 + (index / count) * 360) * Math.PI / 180;
  return {
    x: clamp(50 + Math.cos(angle) * radiusX, narrow ? 15 : 12, narrow ? 85 : 88),
    y: clamp(50 + Math.sin(angle) * radiusY, 13, 78),
  };
}

function getMySeat() {
  if (!state || !activeGuestId) {
    return null;
  }
  return state.seats.find((seat) => seat.guest_id === activeGuestId) || null;
}

function getSeatByIndex(seatIndex) {
  if (!state || seatIndex == null) {
    return null;
  }
  return state.seats.find((seat) => seat.seat_index === seatIndex) || null;
}

function parseCard(card) {
  const suit = card.slice(-1);
  const rank = card.slice(0, -1);
  const symbol = {s: "♠", h: "♥", d: "♦", c: "♣"}[suit] || suit;
  return {rank, symbol, red: suit === "h" || suit === "d"};
}

function formatChips(value) {
  return new Intl.NumberFormat("zh-CN").format(value || 0);
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", second: "2-digit"});
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function statusLabel(status) {
  return {
    waiting: "等待中",
    playing: "游戏中",
    finished: "已结束",
  }[status] || status;
}

function phaseLabel(phase) {
  return {
    waiting: "等待",
    preflop: "翻牌前",
    flop: "翻牌圈",
    turn: "转牌圈",
    river: "河牌圈",
    showdown: "摊牌",
    finished: "已结束",
  }[phase] || phase;
}

function actionLabel(action) {
  return {
    fold: "弃牌",
    check: "过牌",
    call: "跟注",
    bet: "下注",
    raise: "加注",
    all_in: "全下",
  }[action] || action;
}

function handNameLabel(name) {
  return {
    "High Card": "高牌",
    "One Pair": "一对",
    "Two Pair": "两对",
    "Three of a Kind": "三条",
    Straight: "顺子",
    Flush: "同花",
    "Full House": "葫芦",
    "Four of a Kind": "四条",
    "Straight Flush": "同花顺",
    "Royal Flush": "皇家同花顺",
  }[name] || name;
}

function eventLabel(type) {
  return {
    room_created: "创建房间",
    player_joined: "玩家加入",
    player_reconnected: "重新连接",
    player_disconnected: "断线",
    player_left: "离开",
    seat_taken: "坐下",
    stand_up: "站起",
    ready_changed: "准备",
    hand_started: "开始牌局",
    player_action: "玩家行动",
    bot_added: "添加机器人",
    bot_action: "机器人行动",
    hand_finished: "牌局结束",
    ready_break: "阶段休息",
    ai_enabled_changed: "AI 助手",
    borrow_chips: "训练筹码",
    claim_training_chips: "训练筹码",
    training_chips_awarded: "训练筹码",
    game_paused: "暂停",
    game_resumed: "继续",
    time_card_used: "时间卡",
    auto_fold: "超时弃牌",
    game_ended: "结束",
  }[type] || type;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
