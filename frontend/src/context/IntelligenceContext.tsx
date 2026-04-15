/**
 * IntelligenceContext
 *
 * Single source of truth for the AI assistant across the entire application.
 * Both AssistantPage (full view) and AssistantSlideOver (compact panel) consume
 * this context — zero duplicated request logic anywhere.
 *
 * Multi-conversation architecture
 * --------------------------------
 * - Maintains a list of all conversations fetched from GET /ai/conversations/
 * - Tracks the active conversation ID in state (persisted to localStorage)
 * - Loading a conversation fetches its messages from GET /ai/conversations/<id>/messages/
 * - Creating a new conversation calls POST /ai/conversations/new/
 * - Sending a message POSTs to /ai/intelligence/ with the active conversation_id
 *
 * Model availability
 * ------------------
 * - Checks GET /ai/health/ on mount to determine if API key is configured
 * - modelAvailable: null = checking, true = ready, false = unavailable
 * - On API_AUTH_ERROR (503) from /ai/intelligence/ → sets modelAvailable = false
 *
 * Public API
 * ----------
 *   conversations         — list of conversation summaries
 *   conversationsLoaded   — true once the initial list has been fetched
 *   activeConversationId  — UUID of the currently open conversation
 *   messages              — turns in the active conversation
 *   messagesLoaded        — true once history fetch for active conv is done
 *   loading               — true while a request is in flight
 *   modelAvailable        — Ollama health state
 *   createConversation()  — creates new conv, sets it as active
 *   loadConversation(id)  — switches to an existing conversation
 *   sendMessage(text)     — fires a turn against POST /ai/intelligence/
 *   clearConversation()   — removes active conv and clears messages
 *   deleteConversation(id)— deletes a conversation from the list
 *   checkModelStatus()    — re-checks Ollama health
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import client from "../api/client";
import { useAuth } from "./AuthContext";

// ── Shared types ───────────────────────────────────────────────────────────────

export interface IntelligenceSource {
  citation_label: string;
  title:          string;
  author:         string;
  institution:    string;
  year:           number;
  trust_tier:     number;
}

export interface ReasoningFlag {
  flag_id:            string;
  severity:           "high" | "medium" | "low";
  title:              string;
  explanation:        string;
  affected_positions: string[];
  metric_value:       number;
  recommendation:     string;
}

export interface IntelligenceMessage {
  id?:             string;
  role:            "user" | "assistant";
  content:         string;
  timestamp?:      string;
  confidence?:     "high" | "medium" | "low";
  intent?:         string;
  modelUsed?:      string;
  retrievalUsed?:  boolean;
  reasoningFlags?: ReasoningFlag[];
  sources?:        IntelligenceSource[];
  isError?:        boolean;
}

export interface ConversationSummary {
  id:           string;
  title:        string;
  lastQuestion: string;
  updatedAt:    string;
  messageCount: number;
}

// ── Context value shape ────────────────────────────────────────────────────────

interface IntelligenceContextValue {
  // Conversation list
  conversations:       ConversationSummary[];
  conversationsLoaded: boolean;
  loadConversations:   () => Promise<void>;

  // Active conversation
  activeConversationId: string | null;
  messages:             IntelligenceMessage[];
  messagesLoaded:       boolean;
  loadConversation:     (id: string) => Promise<void>;
  createConversation:   () => Promise<string>;
  clearConversation:    () => void;
  deleteConversation:   (id: string) => Promise<void>;

  // Sending
  loading:     boolean;
  sendMessage: (text: string) => Promise<void>;

  // Model status
  modelAvailable:   boolean | null;
  checkModelStatus: () => Promise<void>;
}

// ── Wire types (raw API shapes) ────────────────────────────────────────────────

interface ConversationApiItem {
  id:            string;
  title:         string;
  last_question: string;
  updated_at:    string;
  message_count: number;
}

interface ConversationListResponse {
  conversations: ConversationApiItem[];
}

interface ConversationMessagesResponse {
  id:       string;
  title:    string;
  messages: ApiMessage[];
}

interface ApiMessage {
  id:              string;
  role:            "user" | "assistant";
  content:         string;
  timestamp:       string;
  confidence:      string | null;
  intent:          string | null;
  model_used:      string | null;
  retrieval_used:  boolean | null;
  reasoning_flags: ReasoningFlag[];
  sources:         IntelligenceSource[];
}

interface IntelligenceApiResponse {
  answer:               string;
  sources:              IntelligenceSource[];
  confidence:           "high" | "medium" | "low";
  reasoning_flags:      ReasoningFlag[];
  conversation_id:      string;
  conversation_title:   string;
  model_used:           string;
  retrieval_used:       boolean;
  intent:               string;
  memory_summary_used:  boolean;
}

interface HealthApiResponse {
  api_available:   boolean;
  rag_index_ready: boolean;
  model:           string;
  status:          "ready" | "api_not_configured";
}

interface CreateConvResponse {
  id:    string;
  title: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const ACTIVE_CONV_KEY = "intelligence_active_conversation_id";

// ── Context ────────────────────────────────────────────────────────────────────

const IntelligenceContext = createContext<IntelligenceContextValue | null>(null);

export function IntelligenceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();

  const [conversations,       setConversations]       = useState<ConversationSummary[]>([]);
  const [conversationsLoaded, setConversationsLoaded] = useState(false);
  const [activeConversationId,setActiveConversationId]= useState<string | null>(null);
  const [messages,            setMessages]            = useState<IntelligenceMessage[]>([]);
  const [messagesLoaded,      setMessagesLoaded]      = useState(false);
  const [loading,             setLoading]             = useState(false);
  const [modelAvailable,      setModelAvailable]      = useState<boolean | null>(null);

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // ── Model health check ──────────────────────────────────────────────────────

  const checkModelStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await client.get<HealthApiResponse>("/ai/health/");
      if (mountedRef.current) {
        setModelAvailable(res.data.api_available);
      }
    } catch {
      if (mountedRef.current) setModelAvailable(false);
    }
  }, [isAuthenticated]);

  // ── Load conversation list ──────────────────────────────────────────────────

  const loadConversations = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await client.get<ConversationListResponse>("/ai/conversations/");
      if (!mountedRef.current) return;
      setConversations(
        res.data.conversations.map((c) => ({
          id:           c.id,
          title:        c.title,
          lastQuestion: c.last_question,
          updatedAt:    c.updated_at,
          messageCount: c.message_count,
        }))
      );
    } catch {
      // Non-fatal — list just stays empty
    } finally {
      if (mountedRef.current) setConversationsLoaded(true);
    }
  }, [isAuthenticated]);

  // ── Load a specific conversation's messages ─────────────────────────────────

  const loadConversation = useCallback(async (id: string) => {
    if (!mountedRef.current) return;
    setActiveConversationId(id);
    setMessagesLoaded(false);
    localStorage.setItem(ACTIVE_CONV_KEY, id);

    try {
      const res = await client.get<ConversationMessagesResponse>(
        `/ai/conversations/${id}/messages/`
      );
      if (!mountedRef.current) return;

      const rehydrated: IntelligenceMessage[] = res.data.messages.map((m) => ({
        id:             m.id,
        role:           m.role,
        content:        m.content,
        timestamp:      m.timestamp,
        confidence:     (m.confidence as IntelligenceMessage["confidence"]) ?? undefined,
        intent:         m.intent ?? undefined,
        modelUsed:      m.model_used ?? undefined,
        retrievalUsed:  m.retrieval_used ?? undefined,
        reasoningFlags: m.reasoning_flags ?? [],
        sources:        m.sources ?? [],
      }));
      setMessages(rehydrated);
    } catch {
      setMessages([]);
    } finally {
      if (mountedRef.current) setMessagesLoaded(true);
    }
  }, []);

  // ── Create a new conversation ───────────────────────────────────────────────

  const createConversation = useCallback(async (): Promise<string> => {
    const res = await client.post<CreateConvResponse>("/ai/conversations/new/");
    const newConv: ConversationSummary = {
      id:           res.data.id,
      title:        res.data.title,
      lastQuestion: "",
      updatedAt:    new Date().toISOString(),
      messageCount: 0,
    };
    if (mountedRef.current) {
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(res.data.id);
      setMessages([]);
      setMessagesLoaded(true);
      localStorage.setItem(ACTIVE_CONV_KEY, res.data.id);
    }
    return res.data.id;
  }, []);

  // ── Delete a conversation ───────────────────────────────────────────────────

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await client.delete(`/ai/conversations/${id}/messages/`);
    } catch {
      // Ignore errors — remove from local state regardless
    }
    if (mountedRef.current) {
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConversationId === id) {
        setActiveConversationId(null);
        setMessages([]);
        setMessagesLoaded(true);
        localStorage.removeItem(ACTIVE_CONV_KEY);
      }
    }
  }, [activeConversationId]);

  // ── Clear active conversation (from UI without deleting) ────────────────────

  const clearConversation = useCallback(() => {
    setActiveConversationId(null);
    setMessages([]);
    setMessagesLoaded(true);
    localStorage.removeItem(ACTIVE_CONV_KEY);
  }, []);

  // ── Send a message ──────────────────────────────────────────────────────────

  const sendMessage = useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || loading) return;

    // Optimistically append the user message
    const userMsg: IntelligenceMessage = {
      role:      "user",
      content:   q,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await client.post<IntelligenceApiResponse>("/ai/intelligence/", {
        message:         q,
        conversation_id: activeConversationId,
      });

      const d = res.data;

      // Update active conversation ID if new one was created
      if (d.conversation_id && d.conversation_id !== activeConversationId) {
        if (mountedRef.current) {
          setActiveConversationId(d.conversation_id);
          localStorage.setItem(ACTIVE_CONV_KEY, d.conversation_id);
        }
      }

      // Refresh the conversation list to show updated title + updated_at
      void loadConversations();

      const assistantMsg: IntelligenceMessage = {
        role:           "assistant",
        content:        d.answer,
        timestamp:      new Date().toISOString(),
        confidence:     d.confidence,
        intent:         d.intent,
        modelUsed:      d.model_used,
        retrievalUsed:  d.retrieval_used,
        reasoningFlags: d.reasoning_flags ?? [],
        sources:        d.sources ?? [],
      };

      if (mountedRef.current) {
        setMessages((prev) => [...prev, assistantMsg]);
        setModelAvailable(true);
      }

    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: { error?: string; message?: string } };
      };
      const status    = axiosErr.response?.status;
      const serverErr = axiosErr.response?.data?.error;
      const serverMsg = axiosErr.response?.data?.message;

      // Mark assistant unavailable only on auth config errors
      if (status === 503 && serverErr === "API_AUTH_ERROR") {
        if (mountedRef.current) setModelAvailable(false);
      }

      // Resolve the user-facing error text
      let errorContent: string;
      if (serverErr === "API_AUTH_ERROR") {
        errorContent = "Assistant is not configured. Contact your administrator.";
      } else if (status === 429 || serverErr === "API_RATE_LIMIT") {
        errorContent = "Rate limit reached. Please wait a moment and try again.";
      } else if (status === 504 || serverErr === "MODEL_TIMEOUT") {
        errorContent = "The assistant took too long to respond. Try a shorter question.";
      } else if (status === 503) {
        errorContent = "The assistant service is temporarily unavailable. Please try again.";
      } else if (status === 500) {
        errorContent = "The assistant encountered an error. Please try again.";
      } else {
        errorContent = serverMsg ?? serverErr ?? "Unable to generate a response. Please try again.";
      }

      if (mountedRef.current) {
        setMessages((prev) => [
          ...prev,
          {
            role:    "assistant",
            content: errorContent,
            isError: true,
          },
        ]);
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [loading, activeConversationId, loadConversations]);

  // ── Initialise on auth ──────────────────────────────────────────────────────

  useEffect(() => {
    if (!isAuthenticated) {
      setConversations([]);
      setConversationsLoaded(false);
      setActiveConversationId(null);
      setMessages([]);
      setMessagesLoaded(false);
      setModelAvailable(null);
      return;
    }

    void checkModelStatus();
    void loadConversations().then(() => {
      // Re-open the last active conversation if stored
      const stored = localStorage.getItem(ACTIVE_CONV_KEY);
      if (stored && mountedRef.current) {
        void loadConversation(stored);
      } else if (mountedRef.current) {
        setMessagesLoaded(true);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  return (
    <IntelligenceContext.Provider value={{
      conversations,
      conversationsLoaded,
      loadConversations,
      activeConversationId,
      messages,
      messagesLoaded,
      loadConversation,
      createConversation,
      clearConversation,
      deleteConversation,
      loading,
      sendMessage,
      modelAvailable,
      checkModelStatus,
    }}>
      {children}
    </IntelligenceContext.Provider>
  );
}

export function useIntelligence(): IntelligenceContextValue {
  const ctx = useContext(IntelligenceContext);
  if (!ctx) throw new Error("useIntelligence must be used inside IntelligenceProvider");
  return ctx;
}
