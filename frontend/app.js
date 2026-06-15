// WebSocket bootstrap + dispatch.

const state = {
    ws: null,
    snapshot: null,
    activeChannelId: null,
    streamNode: null,         // 현재 스트리밍 중인 메시지 DOM
    streamChannelId: null,
    slots: [],                // 셋업 단계의 페르소나 슬롯들
};

const STORAGE_KEY = "mafia.setup.v1";

function saveSetup() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
            slots: state.slots.map((s) => ({ ...s, loading: false })),
            theme: document.getElementById("theme")?.value || "",
            sysPrompt: document.getElementById("sys-prompt")?.value || "",
            provider: document.getElementById("provider")?.value || "anthropic",
            anthropicModel: document.getElementById("anthropic-model")?.value || "",
            anthropicKey: document.getElementById("anthropic-key")?.value || "",
            ollamaModel: document.getElementById("ollama-model")?.value || "",
            rc: {
                mafia: +document.getElementById("rc-mafia").value || 0,
                police: +document.getElementById("rc-police").value || 0,
                doctor: +document.getElementById("rc-doctor").value || 0,
                medium: +document.getElementById("rc-medium").value || 0,
                citizen: +document.getElementById("rc-citizen").value || 0,
            },
        }));
    } catch (e) { /* ignore quota */ }
}

function loadSetup() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const data = JSON.parse(raw);
        if (data.rc) {
            document.getElementById("rc-mafia").value = data.rc.mafia ?? 2;
            document.getElementById("rc-police").value = data.rc.police ?? 1;
            document.getElementById("rc-doctor").value = data.rc.doctor ?? 1;
            document.getElementById("rc-medium").value = data.rc.medium ?? 1;
            document.getElementById("rc-citizen").value = data.rc.citizen ?? 2;
        }
        if (data.theme) document.getElementById("theme").value = data.theme;
        if (data.sysPrompt) document.getElementById("sys-prompt").value = data.sysPrompt;
        if (data.provider) document.getElementById("provider").value = data.provider;
        if (data.anthropicModel) document.getElementById("anthropic-model").value = data.anthropicModel;
        if (data.anthropicKey) document.getElementById("anthropic-key").value = data.anthropicKey;
        if (data.ollamaModel) document.getElementById("ollama-model").value = data.ollamaModel;
        if (Array.isArray(data.slots)) state.slots = data.slots;
    } catch (e) { /* ignore corrupt */ }
}

// ---------- Setup view ----------

function readRoleConfig() {
    return {
        mafia: +document.getElementById("rc-mafia").value || 0,
        police: +document.getElementById("rc-police").value || 0,
        doctor: +document.getElementById("rc-doctor").value || 0,
        medium: +document.getElementById("rc-medium").value || 0,
        citizen: +document.getElementById("rc-citizen").value || 0,
    };
}

function updateTotal() {
    const rc = readRoleConfig();
    const total = rc.mafia + rc.police + rc.doctor + rc.medium + rc.citizen;
    document.getElementById("total-count").textContent = total;
    syncSlots(total);
    return total;
}

function syncSlots(total) {
    while (state.slots.length < total) {
        state.slots.push({ name: "", summary: "", style: "", quirks: "", model: "", loading: false });
    }
    while (state.slots.length > total) {
        state.slots.pop();
    }
    saveSetup();
    renderSlots();
}

function renderSlots() {
    const list = document.getElementById("slot-list");
    list.innerHTML = "";
    const providerVal = document.getElementById("provider")?.value || "anthropic";
    const isOllama = providerVal === "ollama";
    state.slots.forEach((s, idx) => {
        const filled = !!s.name.trim();
        const cls = "slot" + (filled ? " filled" : "");
        const card = document.createElement("div");
        card.className = cls;
        card.innerHTML = `
            <div class="slot-head">
                <span>슬롯 ${idx + 1}</span>
                <span class="slot-status">${filled ? s.name : "비어있음"}</span>
            </div>
            ${isOllama
                ? '<select data-k="model" class="slot-model"></select>'
                : '<div class="hint">Anthropic 모드 — 위 카드의 Claude 모델 공유</div>'}
            <input type="text" data-k="name" placeholder="이름 (비우면 모델명 자동)" value="${escapeAttr(s.name)}">
            <div class="slot-actions">
                <button data-act="clear">지우기</button>
            </div>
        `;
        if (isOllama) {
            const sel = card.querySelector('[data-k="model"]');
            populateModelSelect(sel, s.model);
            const expected = deriveNameFromModel(s.model);
            const looksDefault = !s.name || /^유닛\d+$/.test(s.name);
            if (s.model && expected && looksDefault && s.name !== expected) {
                state.slots[idx].name = expected;
                s.name = expected;
                const inp = card.querySelector('[data-k="name"]');
                if (inp) inp.value = expected;
                card.querySelector(".slot-status").textContent = expected;
                card.classList.add("filled");
                saveSetup();
            }
            sel.addEventListener("change", () => {
                const oldModel = state.slots[idx].model;
                state.slots[idx].model = sel.value;
                // 이름이 비었거나 이전 모델의 자동 이름이었다면 새 모델로 갱신.
                // 사용자가 직접 입력한 이름이면 그대로 둠.
                const prevAuto = deriveNameFromModel(oldModel);
                if (!state.slots[idx].name || state.slots[idx].name === prevAuto) {
                    state.slots[idx].name = deriveNameFromModel(sel.value);
                }
                saveSetup();
                renderSlots();
            });
        }
        // 이름 입력 바인딩 — 사용자 커스텀 이름
        const nameInp = card.querySelector('[data-k="name"]');
        if (nameInp) {
            nameInp.addEventListener("input", () => {
                state.slots[idx].name = nameInp.value;
                card.querySelector(".slot-status").textContent = nameInp.value || "비어있음";
                card.classList.toggle("filled", !!nameInp.value.trim());
                saveSetup();
            });
        }
        card.querySelector('[data-act="clear"]').addEventListener("click", () => {
            state.slots[idx] = { name: "", summary: "", style: "", quirks: "", model: "", loading: false };
            saveSetup();
            renderSlots();
        });
        list.appendChild(card);
    });
}

function deriveNameFromModel(model) {
    if (!model) return "";
    // "gemma3:4b" -> "Gemma3"
    // "exaone3.5:2.4b" -> "Exaone3.5"
    // "granite3-moe:3b" -> "Granite3-Moe"
    const base = model.split(":")[0];
    return base.split("-").map((part) => {
        if (!part) return "";
        return part.charAt(0).toUpperCase() + part.slice(1);
    }).join("-");
}

function escapeAttr(s) {
    return String(s ?? "").replace(/"/g, "&quot;");
}

function requestSlotGen(idx) {
    if (!ensureWs()) return;
    sendProviderConfig();
    const existing = state.slots.map((s) => s.name.trim()).filter((n) => n);
    const theme = document.getElementById("theme").value.trim() || null;
    state.slots[idx].loading = true;
    renderSlots();
    send({
        type: "gen_one_persona",
        slot_id: idx,
        existing_names: existing,
        theme,
    });
}

function providerPayload() {
    return {
        provider: document.getElementById("provider").value,
        anthropic_api_key: document.getElementById("anthropic-key").value.trim() || null,
        anthropic_model: document.getElementById("anthropic-model").value.trim()
            || "claude-haiku-4-5-20251001",
        ollama_model: document.getElementById("ollama-model").value.trim() || null,
    };
}

function sendProviderConfig() {
    send({ type: "config_provider", ...providerPayload() });
}

function updateProviderUI() {
    const v = document.getElementById("provider").value;
    document.getElementById("anthropic-model-label").hidden = v !== "anthropic";
    document.getElementById("api-key-label").hidden = v !== "anthropic";
    const hint = document.getElementById("provider-hint");
    if (hint) {
        hint.textContent = v === "ollama"
            ? "Ollama 모드: 페르소나 슬롯에서 모델을 개별 선택합니다."
            : "Anthropic 모드: 모든 유닛이 위 Claude 모델을 공유합니다. 키는 브라우저 localStorage에만 저장.";
    }
    if (v === "ollama") loadOllamaModels();
}

async function loadOllamaModels() {
    try {
        const r = await fetch("/api/ollama/models");
        const data = await r.json();
        state.ollamaModelList = data.ok ? data.models : [];
    } catch (e) {
        state.ollamaModelList = [];
    }
    renderSlots();
}

function populateModelSelect(sel, currentValue) {
    sel.innerHTML = "";
    const models = state.ollamaModelList || [];
    if (!models.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "(Ollama 모델 없음)";
        sel.appendChild(opt);
        return;
    }
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "(모델 선택)";
    sel.appendChild(blank);
    for (const m of models) {
        const sizeMB = m.size ? `(${(m.size / 1024 / 1024 / 1024).toFixed(1)}GB)` : "";
        const opt = document.createElement("option");
        opt.value = m.name;
        opt.textContent = `${m.name} ${sizeMB}`;
        if (m.name === currentValue) opt.selected = true;
        sel.appendChild(opt);
    }
}

function requestAllSlotsGen() {
    if (!ensureWs()) return;
    state.slots.forEach((s, idx) => {
        if (!s.name.trim()) requestSlotGen(idx);
    });
}

function wireSetup() {
    document.querySelectorAll(".role-grid input").forEach((i) => {
        i.addEventListener("input", updateTotal);
    });
    document.getElementById("start-btn").addEventListener("click", onStart);
    updateTotal();
}

function onStart() {
    const rc = readRoleConfig();
    const total = updateTotal();
    if (total < 3) {
        UI.appendLog("최소 3명 이상 필요");
        return;
    }
    const personas = state.slots.map((s) => ({
        name: s.name.trim(),
        summary: s.summary.trim(),
        style: s.style.trim(),
        quirks: s.quirks.trim(),
        model: (s.model || "").trim(),
    }));
    const missing = personas.filter((p) => !p.name).length;
    if (missing > 0) {
        UI.appendLog(`이름 없는 슬롯 ${missing}개 — 채워주세요`);
        return;
    }
    ensureWs();
    send({
        type: "setup",
        persona_mode: "manual",
        count: total,
        role_config: rc,
        personas,
        theme: null,
        system_prompt: document.getElementById("sys-prompt").value.trim() || null,
        ...providerPayload(),
    });
}

// ---------- WebSocket ----------

function ensureWs() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) return true;
    if (state.ws && state.ws.readyState === WebSocket.CONNECTING) return true;
    connect();
    return false;
}

function connect() {
    const url = `ws://${location.host}/ws`;
    const ws = new WebSocket(url);
    state.ws = ws;

    ws.addEventListener("open", () => UI.appendLog("연결됨"));
    ws.addEventListener("message", (ev) => {
        try { handleMessage(JSON.parse(ev.data)); } catch (e) { console.error(e); }
    });
    ws.addEventListener("close", () => UI.appendLog("연결 끊김"));
    ws.addEventListener("error", () => UI.appendLog("WebSocket 에러"));
}

function send(obj) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(obj));
    } else if (state.ws) {
        state.ws.addEventListener("open", () => state.ws.send(JSON.stringify(obj)), { once: true });
    }
}

function handleMessage(msg) {
    switch (msg.type) {
        case "snapshot": applySnapshot(msg.data); break;
        case "chat":
            if (msg.line.channel_id === state.activeChannelId) UI.appendChatLine(msg.line);
            break;
        case "stream_start":
            if (msg.channel_id === state.activeChannelId) {
                state.streamNode = UI.startStreamingBubble(
                    msg.channel_id, msg.speaker_name, msg.speaker_id);
                state.streamChannelId = msg.channel_id;
            }
            break;
        case "stream_delta":
            if (state.streamNode && msg.channel_id === state.streamChannelId) {
                state.streamNode.appendChild(document.createTextNode(msg.delta));
                const area = document.getElementById("chat-area");
                area.scrollTop = area.scrollHeight;
            }
            break;
        case "stream_end":
            if (state.streamNode && msg.channel_id === state.streamChannelId) {
                state.streamNode.classList.remove("streaming");
                // 서버에서 후처리된 최종 텍스트로 교체 (3문장 trim 반영)
                if (msg.line && msg.line.content != null) {
                    const who = state.streamNode.querySelector(".who");
                    state.streamNode.innerHTML = "";
                    if (who) state.streamNode.appendChild(who);
                    state.streamNode.appendChild(document.createTextNode(msg.line.content));
                }
                state.streamNode = null;
                state.streamChannelId = null;
            }
            break;
        case "tally":
            if (state.snapshot) {
                state.snapshot.votes = tallyToVotes(msg.tally, state.snapshot);
                UI.renderTally(state.snapshot);
            }
            break;
        case "approval": {
            const bar = document.getElementById("tally-bar");
            if (bar) {
                bar.innerHTML = `<b>${msg.defendant_name}</b> 찬반 — 찬성 ${msg.yes} / 반대 ${msg.no}`;
            }
            break;
        }
        case "persona_generated":
            applyGeneratedPersona(msg.slot_id, msg.persona);
            break;
        case "persona_failed":
            if (state.slots[msg.slot_id]) {
                state.slots[msg.slot_id].loading = false;
                renderSlots();
            }
            UI.appendLog(`슬롯 ${msg.slot_id + 1} 생성 실패: ${msg.message}`);
            break;
        case "info": UI.appendLog("[INFO] " + msg.message); break;
        case "error": UI.appendLog("[ERR] " + msg.message); break;
    }
}

function applyGeneratedPersona(slotId, persona) {
    if (!state.slots[slotId]) return;
    state.slots[slotId] = {
        name: persona.name || "",
        summary: persona.summary || "",
        style: persona.style || "",
        quirks: persona.quirks || "",
        loading: false,
    };
    saveSetup();
    renderSlots();
}

function tallyToVotes(tally, snap) {
    const out = [];
    for (const [tid, n] of Object.entries(tally)) {
        for (let i = 0; i < n; i++) {
            out.push({ voter_id: `?${i}`, target_id: tid, raw: "" });
        }
    }
    return out;
}

// ---------- Snapshot 적용 ----------

function applySnapshot(snap) {
    state.snapshot = snap;

    const setupVisible = !document.getElementById("setup-view").hidden;
    if (setupVisible && snap.units && snap.units.length > 0) switchToGameView();
    if (state.activeChannelId == null && snap.channels.length > 0) {
        state.activeChannelId = snap.active_channel_id || snap.channels[0].id;
    }
    UI.renderPhaseBar(snap);
    UI.renderChannelTabs(snap, state.activeChannelId, selectChannel);
    UI.renderUnitPanel(snap, panelHandlers());
    UI.renderTally(snap);
}

function refreshChatForActiveChannel() {
    const area = document.getElementById("chat-area");
    if (area) area.innerHTML = "";
}

function selectChannel(id) {
    if (id === state.activeChannelId) return;
    state.activeChannelId = id;
    send({ type: "set_active_channel", channel_id: id });
    refreshChatForActiveChannel();
}

function panelHandlers() {
    return {
        killUnit: (uid) => send({ type: "kill_unit", unit_id: uid }),
        speakInActive: (uid) => {
            const ch = state.activeChannelId;
            if (!ch) return;
            send({ type: "speak_in_channel", unit_id: uid, channel_id: ch });
        },
        summonDead: (uid) => {
            const ch = state.activeChannelId;
            if (!ch || !ch.startsWith("medium:")) {
                UI.appendLog("영매 채널을 먼저 활성화하세요");
                return;
            }
            send({ type: "summon_dead", medium_channel_id: ch, dead_unit_id: uid });
            send({ type: "speak_dead", dead_unit_id: uid, medium_channel_id: ch });
        },
        toggleFlag: (uid, flag, value) =>
            send({ type: "set_night_flag", unit_id: uid, flag, value }),
    };
}

// ---------- 게임 화면 ----------

function switchToGameView() {
    document.getElementById("setup-view").hidden = true;
    document.getElementById("game-view").hidden = false;

    document.querySelectorAll(".phase-bar [data-cmd]").forEach((b) => {
        b.addEventListener("click", () => send({ type: b.dataset.cmd }));
    });

    const input = document.getElementById("gm-input");
    const sendGm = () => {
        const v = input.value.trim();
        if (!v || !state.activeChannelId) return;
        send({ type: "gm_say", channel_id: state.activeChannelId, content: v });
        input.value = "";
    };
    document.getElementById("gm-send").addEventListener("click", sendGm);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendGm(); });
}

// ---------- 부트스트랩 ----------

document.addEventListener("DOMContentLoaded", () => {
    loadSetup();
    wireSetup();
    document.getElementById("sys-prompt").addEventListener("input", saveSetup);
    document.getElementById("provider").addEventListener("change", () => {
        updateProviderUI(); saveSetup(); sendProviderConfig(); renderSlots();
    });
    document.getElementById("anthropic-model").addEventListener("input", saveSetup);
    document.getElementById("anthropic-key").addEventListener("input", saveSetup);
    updateProviderUI();
    connect();   // 셋업 단계부터 WS 연결해야 자동생성 버튼이 즉시 동작
});
