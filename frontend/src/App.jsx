import { useState, useEffect, useRef } from "react";
import "./App.css";

export default function App() {
  // ===== UI State =====
  const [htmlPage, setHtmlPage] = useState("");
  const [chatOpen, setChatOpen] = useState(true);
  const [input, setInput] = useState("");
  const [appliance, setAppliance] = useState(null);
  // --- FIX: Add state to hold the query that triggered a switch suggestion ---
  const [queryToResend, setQueryToResend] = useState("");
  const [messages, setMessages] = useState([
    { from: "system", text: formatText("Hi! I’m Instalily — your AI repair assistant for PartSelect."), html: true },
    { from: "system", text: formatText("Pick an appliance to start: <strong>Dishwasher</strong> or <strong>Refrigerator</strong>."), html: true },
  ]);
  const [loading, setLoading] = useState(false);
  const [awaitingSwitchChoice, setAwaitingSwitchChoice] = useState(false);
  const [botTyping, setBotTyping] = useState(false);

  // ===== Per-appliance chat history =====
  const [history, setHistory] = useState({
    dishwasher: [],
    refrigerator: [],
  });

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);

  // ===== Load static HTML =====
  useEffect(() => {
    fetch("/Official Dishwasher Parts _ Order Today, Ships Today _ PartSelect.html")
      .then((res) => res.text())
      .then((text) => {
        const clean = text
          .replace(/<script[\s\S]*?<\/script>/gi, "")
          .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
          .replace(/<noscript[\s\S]*?<\/noscript>/gi, "")
          .replace(/on\w+="[^"]*"/gi, "")
          .replace(/<div[^>]*id=".*popup.*"[^>]*>[\s\S]*?<\/div>/gi, "")
          .replace(/<link[^>]+ads[^>]+>/gi, "");
        setHtmlPage(clean);
      });
  }, []);

  // ===== Auto scroll =====
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, botTyping]);

  // ===== Focus management =====
  useEffect(() => {
    if (chatOpen && !awaitingSwitchChoice) {
      setTimeout(() => inputRef.current?.focus(), 250);
    }
  }, [chatOpen, awaitingSwitchChoice]);

  // ===== Message helpers =====
  function pushUser(text) {
    setMessages((m) => [...m, { from: "user", text }]);
  }
  function pushBotHtml(html) {
    setMessages((m) => [...m, { from: "bot", text: formatText(html), html: true }]);
  }
  async function botSay(html, delayMs = 450) {
    setBotTyping(true);
    await sleep(delayMs);
    setBotTyping(false);
    pushBotHtml(html);
  }

  // ===== BACKEND Communication =====
  // --- FIX: Allow passing an appliance override to solve stale state ---
  async function sendToBackend(text, applianceOverride = null) {
    setLoading(true);
    setBotTyping(true);
    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // --- FIX: Use the override if provided, otherwise use component state ---
        body: JSON.stringify({ message: text, appliance: applianceOverride ?? appliance }),
      });
      const data = await res.json();
      setBotTyping(false);

      // 🧠 Handle backend switch suggestion
      if (data.intent === "switch_suggestion") {
        const match = data.response.match(/<strong>(.*?)<\/strong>/i);
        const suggested = match ? match[1].toLowerCase() : null;
        pushBotHtml(data.response);
        if (suggested) {
          // Pass the original text (query) to the confirmation function
          askSwitchConfirmation(suggested, text);
        }
        return;
      }

      // Normal bot reply
      pushBotHtml((data.response || "No response.").trim());
    } catch (err) {
      console.error("Backend error", err);
      setBotTyping(false);
      pushBotHtml("⚠️ Backend not reachable.");
    } finally {
      setLoading(false);
    }
  }

  // ===== Ask user to confirm switch (and resend query if yes) =====
  function askSwitchConfirmation(target, lastQuery) {
    setAwaitingSwitchChoice(true);
    // --- FIX: Save the query that needs to be resent on confirmation ---
    setQueryToResend(lastQuery);
    botSay(
      `You seem to be asking about a ${capitalize(target)}.<br/>Would you like to switch?`,
      200
    );
    setMessages((m) => [
      ...m,
      {
        from: "system",
        text: `
          <div class="switch-options">
            <button class="pill small" id="confirm-switch-${target}">✅ Switch to ${capitalize(target)}</button>
            <button class="pill small" id="cancel-switch">❌ Stay on ${capitalize(appliance ?? "current")}</button>
          </div>
        `,
        html: true,
      },
    ]);
  }

  // ===== Handle dynamic button clicks =====
  useEffect(() => {
    const chat = document.querySelector(".chat-body");
    if (!chat) return;

    const handleClick = async (e) => {
      // ✅ Confirmed switch (backend-suggested)
      if (e.target.id?.startsWith("confirm-switch-")) {
        const target = e.target.id.replace("confirm-switch-", "");
        switchToAppliance(target);
        setAwaitingSwitchChoice(false);
        await sleep(400);
        
        // --- FIX: Resend the *original* query from state, then clear it ---
        if (queryToResend) {
          // --- FIX: Pass the 'target' appliance directly to sendToBackend ---
          await sendToBackend(queryToResend, target);
          setQueryToResend("");
        }
      }

      // ✅ Manual switch from buttons
      else if (e.target.id === "switch-dishwasher") {
        switchToAppliance("dishwasher");
        setAwaitingSwitchChoice(false);
      } else if (e.target.id === "switch-refrigerator") {
        switchToAppliance("refrigerator");
        setAwaitingSwitchChoice(false);
      }

      // ❌ User stays on same appliance
      else if (e.target.id === "stay-here" || e.target.id === "cancel-switch") {
        setAwaitingSwitchChoice(false);
        botSay(`Okay! Staying with <strong>${capitalize(appliance ?? "current")}</strong>.`, 200);
      
        // 🧩 Tell backend not to suggest again for this session
        // --- FIX: Add 'await' to the fetch call ---
        await fetch("http://127.0.0.1:8000/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: "user refused switch",
            appliance: appliance,
          }),
        });
      }
    }; // <-- *** FIX: The handleClick function definition ends HERE ***

    // --- FIX: These lines must be *outside* the handleClick definition ---
    chat.addEventListener("click", handleClick);
    return () => chat.removeEventListener("click", handleClick);

  // --- FIX: Add queryToResend to the dependency array ---
  }, [appliance, messages, queryToResend]);

  // ===== Offer manual switch option =====
  function offerSwitchOption(target) {
    setAwaitingSwitchChoice(true);
    botSay(`Would you like to switch to <strong>${capitalize(target)}</strong>?`, 200);
    setMessages((m) => [
      ...m,
      {
        from: "system",
        text: `
          <div class="switch-options">
            <button class="pill small" id="switch-${target}">✅ Switch to ${capitalize(target)}</button>
            <button class="pill small" id="stay-here">❌ Stay on ${capitalize(appliance ?? "current")}</button>
          </div>
        `,
        html: true,
      },
    ]);
  }

  // ===== Switch appliances and restore context =====
  function switchToAppliance(target) {
    const targetKey = target.toLowerCase();
    
    // --- NOTE: This is the logic you requested to clear history on switch ---
    setHistory({ dishwasher: [], refrigerator: [] });

    setMessages(() => {
      // const saved = history[targetKey]; // <-- REMOVED
      // if (saved?.length) return saved; // <-- REMOVED
      return [
        { from: "system", text: formatText(`Switched to <strong>${capitalize(targetKey)}</strong> assistance!`), html: true },
        {
          from: "bot",
          text: formatText(
            `We’re now in <strong>${capitalize(targetKey)}</strong> mode. Ask me about parts, compatibility, or repairs.`
          ),
          html: true,
        },
      ];
    });

    setAppliance(targetKey);
    setAwaitingSwitchChoice(false);
    setInput("");
  }

  // ===== Send message handler =====
  async function sendMessage() {
    const text = input.trim();
    if (!text) return;

    pushUser(text);
    setInput("");

    if (!appliance) {
      setAwaitingSwitchChoice(true);
      botSay("Please choose an appliance to begin:", 150);
      setMessages((m) => [
        ...m,
        {
          from: "system",
          text: `
            <div class="switch-options">
              <button class="pill small" id="switch-refrigerator">🧊 Refrigerator</button>
              <button class="pill small" id="switch-dishwasher">🧼 Dishwasher</button>
            </div>
          `,
          html: true,
        },
      ]);
      return;
    }

    // This call is fine, it will use the current 'appliance' state
    await sendToBackend(text); 
  }

  // ===== Floating switch button =====
  const floatingSwitchButton = appliance && (
    <button
      className="floating-switch"
      onClick={() =>
        offerSwitchOption(appliance === "dishwasher" ? "refrigerator" : "dishwasher")
      }
      title="Switch appliance"
    >
      🔁 {appliance === "dishwasher" ? "Refrigerator" : "Dishwasher"}
    </button>
  );

  // ===== Intro card =====
  function renderIntroCard() {
    if (appliance) return null;
    return (
      <div className="intro-card">
        <div className="intro-title">Select your appliance to begin:</div>
        <div className="appliance-pills">
          <button className="pill" onClick={() => switchToAppliance("refrigerator")}>
            🧊 Refrigerator
          </button>
          <button className="pill" onClick={() => switchToAppliance("dishwasher")}>
            🧼 Dishwasher
          </button>
        </div>
      </div>
    );
  }

  // ===== Utils =====
  function capitalize(s) {
    if (!s) return s;
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
  function formatText(s) {
    if (!s) return s;
    return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br/>");
  }

  // ===== Render =====
  return (
    <div className="page-container">
      <div className="scroll-banner">⚠️ Demo Only – Not affiliated with PartSelect.</div>

      <iframe className="html-wrapper" srcDoc={htmlPage} title="Static PartSelect Page" />

      {!chatOpen && (
        <div className="chat-bar" onClick={() => setChatOpen(true)}>
          💬 Chat with AI
        </div>
      )}

      <div className={`chat-window ${chatOpen ? "open" : "closed"}`}>
        <div className="chat-header">
          AI Repair Assistant {appliance ? `· ${capitalize(appliance)}` : ""}
          <span className="close-btn" onClick={() => setChatOpen(false)}>✕</span>
        </div>

        {floatingSwitchButton}

        <div className="chat-body">
          {renderIntroCard()}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.from}`}>
              {m.html ? (
                <div dangerouslySetInnerHTML={{ __html: m.text }} />
              ) : (
                m.text
              )}
            </div>
          ))}
          {botTyping && <div className="msg bot">…</div>}
          {loading && !botTyping && <div className="msg bot">⏳ Thinking...</div>}
          <div ref={chatEndRef} />
        </div>

        <div className="chat-input">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder={
              awaitingSwitchChoice
                ? "Please choose an option above…"
                : appliance
                ? "Type your question…"
                : "Select Dishwasher or Refrigerator to start"
            }
            disabled={!appliance || awaitingSwitchChoice || loading}
            />
          <button onClick={sendMessage} disabled={awaitingSwitchChoice || loading}>
            {loading ? "..." : "Send"}
          </button>
        </div>

        <div className="note">
          Context-Aware Assistant · Intelligent Switching · Floating Mode Toggle
        </div>
      </div>
    </div>
  );
}