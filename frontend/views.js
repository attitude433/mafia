// DOM rendering helpers — pure-ish functions invoked by app.js.

const ROLE_LABEL = {
    mafia: "마피아",
    police: "경찰",
    doctor: "의사",
    medium: "영매",
    citizen: "시민",
};

const PHASE_LABEL = {
    setup: "SETUP",
    day_discussion: "DAY 토론",
    day_voting: "DAY 투표",
    night: "NIGHT",
    ended: "종료",
};

function el(tag, props = {}, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
        if (k === "class") e.className = v;
        else if (k === "dataset") Object.assign(e.dataset, v);
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else if (k === "html") e.innerHTML = v;
        else if (v === true) e.setAttribute(k, "");
        else if (v === false || v == null) {}
        else e.setAttribute(k, v);
    }
    for (const c of children.flat()) {
        if (c == null) continue;
        e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return e;
}

function renderPhaseBar(snapshot) {
    document.getElementById("phase-label").textContent =
        PHASE_LABEL[snapshot.phase] || snapshot.phase;
    document.getElementById("day-label").textContent = `Day ${snapshot.day}`;
}

function renderChannelTabs(snapshot, activeId, onSelect) {
    const tabs = document.getElementById("channel-tabs");
    tabs.innerHTML = "";
    for (const ch of snapshot.channels) {
        const t = el(
            "div",
            {
                class: "tab" + (ch.id === activeId ? " active" : ""),
                onclick: () => onSelect(ch.id),
            },
            ch.label,
            el("span", { class: `tab-kind ${ch.kind}` }, ch.kind),
        );
        tabs.appendChild(t);
    }
}

function renderChat(lines) {
    const area = document.getElementById("chat-area");
    area.innerHTML = "";
    for (const ln of lines) appendChatLine(ln);
    area.scrollTop = area.scrollHeight;
}

function appendChatLine(line) {
    const area = document.getElementById("chat-area");
    const klass = "msg " + line.speaker_kind;
    const node = el(
        "div",
        { class: klass, dataset: { id: line.speaker_id, ts: line.ts } },
        el("span", { class: "who" }, line.speaker_name),
        document.createTextNode(line.content),
    );
    area.appendChild(node);
    area.scrollTop = area.scrollHeight;
    return node;
}

function startStreamingBubble(channelId, speakerName, speakerId) {
    const area = document.getElementById("chat-area");
    const node = el(
        "div",
        { class: "msg unit streaming", dataset: { stream: "1", id: speakerId } },
        el("span", { class: "who" }, speakerName),
        document.createTextNode(""),
    );
    area.appendChild(node);
    area.scrollTop = area.scrollHeight;
    return node;
}

function renderUnitPanel(snapshot, handlers) {
    const panel = document.getElementById("unit-panel");
    panel.innerHTML = "";
    const speakingId = snapshot.speaking_unit_id;
    for (const u of snapshot.units) {
        const cls =
            "unit-card" +
            (!u.alive ? " dead" : "") +
            (u.id === speakingId ? " speaking" : "");
        const flags = el(
            "div",
            { class: "flags" },
            flagChip(u, "targeted_by_mafia", "표적", "mafia", handlers),
            flagChip(u, "protected_by_doctor", "보호", "doctor", handlers),
            flagChip(u, "investigated_by_police", "조사", "police", handlers),
        );
        const actions = el(
            "div",
            { class: "actions" },
            el(
                "button",
                { onclick: () => handlers.killUnit(u.id), disabled: !u.alive },
                "즉시 사망",
            ),
            el(
                "button",
                { onclick: () => handlers.speakInActive(u.id), disabled: !u.alive },
                "이 채널서 발언",
            ),
            u.alive
                ? null
                : el(
                      "button",
                      { onclick: () => handlers.summonDead(u.id) },
                      "영매 호출",
                  ),
        );
        panel.appendChild(
            el(
                "div",
                { class: cls },
                el("div", { class: "name" }, (u.persona && u.persona.name) || "이름없음", " ",
                   el("span", { class: "role" }, "(" + ROLE_LABEL[u.role] + ")")),
                el("div", { class: "summary" }, u.persona.summary || ""),
                flags,
                actions,
            ),
        );
    }
}

function flagChip(unit, key, label, color, handlers) {
    const on = unit.night && unit.night[key];
    return el(
        "span",
        {
            class: `flag ${color}` + (on ? " on" : ""),
            onclick: () => handlers.toggleFlag(unit.id, key, !on),
        },
        label,
    );
}

function renderTally(snapshot) {
    const bar = document.getElementById("tally-bar");
    if (!snapshot.votes || snapshot.votes.length === 0) {
        bar.textContent = "투표 없음";
        return;
    }
    const counts = {};
    const names = {};
    for (const u of snapshot.units) names[u.id] = u.name;
    for (const v of snapshot.votes) {
        const t = v.target_id || "(기권/파싱실패)";
        counts[t] = (counts[t] || 0) + 1;
    }
    bar.innerHTML = "";
    for (const [k, n] of Object.entries(counts).sort((a, b) => b[1] - a[1])) {
        bar.appendChild(
            el("span", { class: "vote-item" }, `${names[k] || k}: ${n}표`),
        );
    }
}

function appendLog(text) {
    const setupLog = document.getElementById("setup-log");
    const gameLog = document.getElementById("game-log");
    const line = text + "\n";
    if (setupLog && !setupLog.closest(".view").hidden) {
        setupLog.textContent += line;
        setupLog.scrollTop = setupLog.scrollHeight;
    }
    if (gameLog && !gameLog.closest(".view").hidden) {
        gameLog.textContent += line;
        gameLog.scrollTop = gameLog.scrollHeight;
    }
}

window.UI = {
    renderPhaseBar,
    renderChannelTabs,
    renderChat,
    appendChatLine,
    startStreamingBubble,
    renderUnitPanel,
    renderTally,
    appendLog,
};
