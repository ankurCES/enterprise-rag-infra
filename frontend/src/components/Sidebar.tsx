import React, { useEffect, useState } from "react";
import { useMsal } from "@azure/msal-react";
import axios from "axios";

interface Session {
  id: string;
  email: string;
  created_at: string;
}

interface SidebarProps {
  onSelectSession: (id: string) => void;
  selectedSessionId?: string;
}

const Sidebar: React.FC<SidebarProps> = ({ onSelectSession, selectedSessionId }) => {
  const { instance, accounts } = useMsal();
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await axios.get(`${import.meta.env.VITE_API_URL}/sessions`, {
          headers: {
            Authorization: `Bearer ${sessionStorage.getItem("accessToken")}`,
          },
        });
        setSessions(response.data);
      } catch (error) {
        console.error("Error fetching sessions:", error);
      }
    };

    if (accounts.length > 0) {
      fetchSessions();
    }
  }, [accounts]);

  const handleLogout = () => {
    instance.logoutPopup().catch((e) => {
      console.error(e);
    });
  };

  return (
    <div className="w-64 bg-gray-900 text-white flex flex-col h-screen border-r border-gray-800">
      <div className="p-4 border-b border-gray-800 flex justify-between items-center">
        <h1 className="text-xl font-bold">Odin RAG</h1>
        <button
          onClick={() => onSelectSession("")}
          className="bg-blue-600 hover:bg-blue-700 text-white px-2 py-1 rounded text-sm transition"
        >
          New Chat
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => onSelectSession(session.id)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm truncate transition ${
              selectedSessionId === session.id ? "bg-gray-800 ring-1 ring-gray-700" : "hover:bg-gray-800"
            }`}
          >
            {session.id.substring(0, 8)}... - {new Date(session.created_at).toLocaleDateString()}
          </button>
        ))}
      </div>

      <div className="p-4 border-t border-gray-800 bg-gray-950">
        <div className="text-xs text-gray-400 mb-2 truncate">{accounts[0]?.username}</div>
        <button
          onClick={handleLogout}
          className="w-full bg-gray-800 hover:bg-red-900/50 hover:text-red-400 text-gray-300 py-2 rounded-lg text-sm transition"
        >
          Sign Out
        </button>
      </div>
    </div>
  );
};

export default Sidebar;
