import { useState } from "react";

import { chatWithAgent } from "../api/client";
import { Button, Divider, Spinner } from "./ui";

interface ChatPanelProps {
  datasetId: number;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export default function ChatPanel({ datasetId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!message.trim()) {
      return;
    }

    const userMessage: ChatMessage = { role: "user", text: message.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setMessage("");
    setLoading(true);

    try {
      const response = await chatWithAgent(datasetId, userMessage.text);
      setMessages((prev) => [...prev, { role: "assistant", text: response.reply }]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Agent yanıtı alınırken hata oluştu." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">AI Agent</h3>
        {loading && <Spinner size="sm" />}
      </div>
      <Divider className="my-3" />

      <div className="max-h-[280px] space-y-2 overflow-y-auto pr-1 text-sm">
        {messages.length === 0 ? (
          <p className="text-muted">Agent ile sohbet edebilirsin. Örn: “Bu veri seti ne anlatıyor?”</p>
        ) : (
          messages.map((item, index) => (
            <div key={`${item.role}-${index}`} className="rounded-lg border border-border bg-surface2 p-2">
              <p className="text-xs text-muted">{item.role === "user" ? "Sen" : "Agent"}</p>
              <p className="mt-1 text-text">{item.text}</p>
            </div>
          ))
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          className="h-10 flex-1 rounded-lg border border-border bg-surface2 px-3 text-sm text-text placeholder:text-muted outline-none focus:border-accentDim"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Mesaj yaz..."
        />
        <Button variant="ghost" onClick={sendMessage} disabled={loading}>
          Gönder
        </Button>
      </div>
    </div>
  );
}
