import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { PortfolioProvider } from "./context/PortfolioContext";
import { ToastProvider } from "./context/ToastContext";
import { IntelligenceProvider } from "./context/IntelligenceContext";
import ProtectedRoute from "./routes/ProtectedRoute";
import AppShell from "./components/AppShell";
import ToastContainer from "./components/ToastContainer";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import PortfolioPage from "./pages/PortfolioPage";
import TradePage from "./pages/TradePage";
import MarketPage from "./pages/MarketPage";
import ImportPage from "./pages/ImportPage";
import AssistantPage from "./pages/AssistantPage";
import ActivityPage from "./pages/ActivityPage";
import MarketIntelligencePage from "./pages/MarketIntelligencePage";

function ProtectedShell() {
  return (
    <ProtectedRoute>
      <AppShell />
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <PortfolioProvider>
            {/* IntelligenceProvider wraps all protected routes so AssistantPage
                and AssistantSlideOver share one conversation state and session */}
            <IntelligenceProvider>
            <Routes>
              <Route path="/login" element={<Login />} />

              <Route element={<ProtectedShell />}>
                <Route path="/overview"   element={<Overview />} />
                <Route path="/portfolio"  element={<PortfolioPage />} />
                <Route path="/trade"      element={<TradePage />} />
                <Route path="/market"     element={<MarketPage />} />
                <Route path="/import"     element={<ImportPage />} />
                <Route path="/assistant"   element={<AssistantPage />} />
                <Route path="/activity"    element={<ActivityPage />} />
                <Route path="/intelligence" element={<MarketIntelligencePage />} />
              </Route>

              {/* Legacy + catch-all → overview */}
              <Route path="/dashboard" element={<Navigate to="/overview" replace />} />
              <Route path="*"          element={<Navigate to="/overview" replace />} />
            </Routes>

            {/* Global toast — outside routing so it survives navigation */}
            <ToastContainer />
            </IntelligenceProvider>
          </PortfolioProvider>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
