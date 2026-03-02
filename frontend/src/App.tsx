import React, { useState, useEffect } from "react";
import { AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from "@azure/msal-react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import { loginRequest } from "./authConfig";

const App: React.FC = () => {
  const { instance, accounts } = useMsal();
  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>();

  useEffect(() => {
    // Acquire Access Token for the backend
    const acquireToken = async () => {
      try {
        const response = await instance.acquireTokenSilent({
          ...loginRequest,
          account: accounts[0],
        });
        sessionStorage.setItem("accessToken", response.accessToken);
      } catch (error) {
        console.error("Token acquisition error:", error);
      }
    };

    if (accounts.length > 0) {
      acquireToken();
    }
  }, [accounts, instance]);

  const handleLogin = () => {
    instance.loginPopup(loginRequest).catch((e) => {
      console.error(e);
    });
  };

  return (
    <div className="flex h-screen w-full bg-gray-950 font-sans text-gray-200 antialiased overflow-hidden">
      <AuthenticatedTemplate>
        <Sidebar onSelectSession={setSelectedSessionId} selectedSessionId={selectedSessionId} />
        <main className="flex-1 flex flex-col min-w-0">
          <ChatWindow sessionId={selectedSessionId} setSessionId={setSelectedSessionId} />
        </main>
      </AuthenticatedTemplate>

      <UnauthenticatedTemplate>
        <div className="flex flex-col items-center justify-center w-full h-full space-y-8 bg-gray-950 px-6">
          <div className="text-center space-y-2">
            <h1 className="text-4xl font-bold tracking-tight text-white sm:text-6xl">Odin RAG</h1>
            <p className="text-lg text-gray-400">Enterprise Engineering Document Intelligence</p>
          </div>
          
          <div className="w-full max-w-sm p-8 bg-gray-900 border border-gray-800 rounded-3xl shadow-2xl space-y-6">
            <div className="space-y-2 text-center">
              <p className="text-sm font-medium text-gray-400 italic">"Verify documents via Microsoft SSO"</p>
            </div>
            <button
              onClick={handleLogin}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-4 rounded-2xl transition-all shadow-lg hover:shadow-blue-500/20 active:scale-95 flex items-center justify-center space-x-2"
            >
              <img src="https://upload.wikimedia.org/wikipedia/commons/4/44/Microsoft_logo.svg" className="h-5 w-5 mr-2" alt="Microsoft" />
              Sign in with Microsoft
            </button>
          </div>
          
          <p className="text-xs text-gray-600 max-w-xs text-center">
            This system is for authorized engineering use only. All access is logged via Azure AD.
          </p>
        </div>
      </UnauthenticatedTemplate>
    </div>
  );
};

export default App;
