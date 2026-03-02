import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import axios from "axios";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatWindowProps {
  sessionId?: string;
  setSessionId: (id: string) => void;
}

const ChatWindow: React.FC<ChatWindowProps> = ({ sessionId, setSessionId }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      if (sessionId) {
        try {
          const response = await axios.get(`${import.meta.env.VITE_API_URL}/history/${sessionId}`, {
            headers: {
              Authorization: `Bearer ${sessionStorage.getItem("accessToken")}`,
            },
          });
          setMessages(response.data.history);
        } catch (error) {
          console.error("Error fetching history:", error);
        }
      } else {
        setMessages([]);
      }
    };

    fetchHistory();
  }, [sessionId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    let assistantMessage: Message = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${sessionStorage.getItem("accessToken")}`,
        },
        body: JSON.stringify({ message: input, session_id: sessionId }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader");

      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.replace("data: ", "");
            if (dataStr === "[DONE]") {
              setIsLoading(false);
              continue;
            }
            try {
              const data = JSON.parse(dataStr);
              if (data.content) {
                assistantMessage.content += data.content;
                setMessages((prev) => {
                  const newMessages = [...prev];
                  newMessages[newMessages.length - 1] = { ...assistantMessage };
                  return newMessages;
                });
              }
            } catch (e) {
              console.error("Error parsing JSON:", e);
            }
          }
        }
      }
    } catch (error) {
      console.error("Error sending message:", error);
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen bg-gray-950 text-white">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 space-y-4">
            <h2 className="text-2xl font-semibold">How can I help you today?</h2>
            <p className="max-w-md text-center">Ask me anything about engineering documents on the SMB share.</p>
          </div>
        )}
        
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-3xl p-4 rounded-2xl ${m.role === "user" ? "bg-blue-600/20 text-blue-100" : "bg-gray-900 border border-gray-800"}`}>
              <ReactMarkdown className="prose prose-invert prose-sm max-w-none">
                {m.content}
              </ReactMarkdown>
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 md:p-8 border-t border-gray-800 bg-gray-950">
        <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto flex items-end space-x-2 bg-gray-900 rounded-2xl p-2 border border-gray-800 shadow-xl focus-within:border-blue-500 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage(e);
              }
            }}
            placeholder="Ask a question..."
            className="flex-1 bg-transparent border-none focus:ring-0 text-white p-2 resize-none max-h-48"
            rows={1}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 text-white p-2 rounded-xl transition-all"
          >
            Send
          </button>
        </form>
        <div className="text-[10px] text-gray-500 mt-2 text-center">
          Odin RAG may provide inaccurate information. Always verify source citations.
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
