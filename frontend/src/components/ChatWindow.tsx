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
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    let assistantContent = "";
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${sessionStorage.getItem("accessToken")}`,
        },
        body: JSON.stringify({ message: input, session_id: sessionId }),
      });

      if (!response.ok) throw new Error("Backend request failed");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || ""; // Keep the last incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.replace("data: ", "").trim();
              if (dataStr === "[DONE]") {
                setIsLoading(false);
                continue;
              }
              try {
                const data = JSON.parse(dataStr);
                if (data.content) {
                  assistantContent += data.content;
                  setMessages((prev) => {
                    const next = [...prev];
                    next[next.length - 1] = { role: "assistant", content: assistantContent };
                    return next;
                  });
                }
                if (data.error) {
                   assistantContent += `\n\n**Error:** ${data.error}`;
                   setIsLoading(false);
                }
              } catch (e) {
                console.warn("Incomplete JSON chunk received", dataStr);
              }
            }
          }
        }
      }
    } catch (error) {
      console.error("Streaming Error:", error);
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", content: "Sorry, I encountered an error processing your request." };
        return next;
      });
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen bg-gray-950 text-white">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 scroll-smooth">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 space-y-4 animate-in fade-in duration-700">
            <h2 className="text-3xl font-bold text-white tracking-tight">Odin Engineering Intelligence</h2>
            <p className="max-w-md text-center text-gray-500">Secure RAG access to engineering documentation, specifications, and CAD data.</p>
          </div>
        )}
        
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"} animate-in slide-in-from-bottom-2`}>
            <div className={`max-w-3xl p-5 rounded-3xl shadow-lg ${
              m.role === "user" 
                ? "bg-blue-600 text-white rounded-br-none" 
                : "bg-gray-900 border border-gray-800 text-gray-200 rounded-bl-none"
            }`}>
              <ReactMarkdown className="prose prose-invert prose-blue max-w-none prose-pre:bg-gray-800 prose-pre:p-4 prose-code:text-blue-300">
                {m.content}
              </ReactMarkdown>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start animate-pulse">
            <div className="bg-gray-900 border border-gray-800 p-4 rounded-2xl">
              <div className="flex space-x-2">
                <div className="w-2 h-2 bg-gray-600 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-gray-600 rounded-full animate-bounce delay-75"></div>
                <div className="w-2 h-2 bg-gray-600 rounded-full animate-bounce delay-150"></div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="p-4 md:p-8 bg-gradient-to-t from-gray-950 to-transparent">
        <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto flex items-end space-x-3 bg-gray-900 rounded-3xl p-3 border border-gray-800 focus-within:ring-2 focus-within:ring-blue-500/50 focus-within:border-blue-500 transition-all shadow-2xl">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage(e);
              }
            }}
            placeholder="Search engineering documents..."
            className="flex-1 bg-transparent border-none focus:ring-0 text-gray-100 p-2 resize-none max-h-48 text-sm md:text-base"
            rows={1}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-600 text-white px-5 py-2.5 rounded-2xl font-semibold transition-all shadow-lg active:scale-95"
          >
            {isLoading ? "Thinking..." : "Send"}
          </button>
        </form>
        <div className="text-[10px] text-gray-600 mt-4 text-center font-medium tracking-wide uppercase">
          Authorized Engineering Access Only • Verified via Azure AD SSO
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
