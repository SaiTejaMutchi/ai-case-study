
import React, { useState } from "react";

export default function ChatAssistant() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);

  async function sendMessage() {
    if (!input.trim()) return;

    const userText = input.trim();
    setMessages((m) => [...m, { role: "user", content: userText }]);
    setInput("");

    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMessages((m) => [...m, { role: "assistant", content: data.response }]);
    } catch (e) {
      console.error(e);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "⚠️ Backend error. Is FastAPI running on :8000?" },
      ]);
    }
  }

  return (
    <div className="bg-white rounded-xl shadow border p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Ask about parts, leaks, installs, compatibility
      </h2>

      <div className="h-80 overflow-y-auto space-y-3 border rounded p-3 bg-gray-50">
        {messages.length === 0 && (
          <div className="text-gray-500 text-sm">
            Try: “My dishwasher is leaking”, “Show details for PS11752778”, “How to install PS11752778”.
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`px-3 py-2 rounded max-w-[80%] ${
              m.role === "user" ? "ml-auto bg-blue-100" : "mr-auto bg-white border"
            }`}
          >
            {m.content}
          </div>
        ))}
      </div>

      <div className="mt-4 flex">
        <input
          className="flex-1 border rounded-l px-3 py-2 focus:outline-none"
          placeholder="Type your question…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
        />
        <button
          className="bg-teal-700 text-white px-4 py-2 rounded-r hover:bg-teal-800"
          onClick={sendMessage}
        >
          Send
        </button>
      </div>
    </div>
  );
}
