import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../auth/AuthContext';
import AIConsentBanner from './AIConsentBanner';
import styles from './ChatPanel.module.css';

/**
 * Message interface matching backend format
 */
interface Message {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * ChatPanel component props
 */
interface ChatPanelProps {
  conversationId?: string;
}

/**
 * ChatPanel: Main chat component with streaming support
 * Handles real-time AI chat with message history and markdown rendering
 */
export const ChatPanel: React.FC<ChatPanelProps> = ({ conversationId: initialConversationId }) => {
  // State management
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string>(
    initialConversationId || generateUUID()
  );
  const [isExpanded, setIsExpanded] = useState(true);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auth hook
  const { getToken, isSignedIn } = useAuth();

  /**
   * Auto-scroll to the latest message
   */
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  /**
   * Generate a UUID for conversations
   */
  function generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /**
   * Handle sending a message with SSE streaming
   */
  const handleSendMessage = useCallback(
    async (userMessage: string) => {
      if (!userMessage.trim()) return;
      if (!isSignedIn) {
        setError('Please sign in to use the chat');
        return;
      }

      try {
        setError(null);
        setLoading(true);

        // Add user message to history
        const updatedMessages: Message[] = [
          ...messages,
          { role: 'user', content: userMessage },
        ];
        setMessages(updatedMessages);
        setInput('');

        // Get auth token
        const token = getToken();

        // Prepare the request
        const requestBody = {
          messages: updatedMessages,
          conversation_id: conversationId,
          tools: undefined, // Optional: tools can be added later
        };

        // Create abort controller for cancellation
        abortControllerRef.current = new AbortController();

        // POST to the AI chat endpoint
        const response = await fetch('/api/ai/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify(requestBody),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        if (!response.body) {
          throw new Error('No response body');
        }

        // Handle SSE streaming
        let assistantMessage = '';
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // Add empty assistant message placeholder
        const messagesWithPlaceholder: Message[] = [
          ...updatedMessages,
          { role: 'assistant', content: '' },
        ];
        setMessages(messagesWithPlaceholder);

        let buffer = '';

        try {
          while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE events
            const lines = buffer.split('\n\n');
            buffer = lines[lines.length - 1]; // Keep incomplete line in buffer

            for (let i = 0; i < lines.length - 1; i++) {
              const line = lines[i];

              // Skip empty lines and comments
              if (!line || line.startsWith(':')) continue;

              // Parse SSE format: "data: {...}"
              if (line.startsWith('data: ')) {
                try {
                  const dataStr = line.slice(6); // Remove "data: " prefix
                  const data = JSON.parse(dataStr);

                  if (data.type === 'text' && data.token) {
                    assistantMessage += data.token;

                    // Update assistant message in real-time
                    setMessages((prevMessages) => {
                      const updated = [...prevMessages];
                      if (updated.length > 0) {
                        updated[updated.length - 1] = {
                          role: 'assistant',
                          content: assistantMessage,
                        };
                      }
                      return updated;
                    });
                  } else if (data.type === 'done') {
                    // Stream complete
                    break;
                  } else if (data.type === 'error') {
                    throw new Error(data.message || 'Unknown error from AI service');
                  }
                } catch (parseError) {
                  console.error('Failed to parse SSE event:', parseError);
                }
              }
            }
          }

          // Final buffer processing
          if (buffer.trim()) {
            if (buffer.startsWith('data: ')) {
              try {
                const dataStr = buffer.slice(6);
                const data = JSON.parse(dataStr);

                if (data.type === 'text' && data.token) {
                  assistantMessage += data.token;
                  setMessages((prevMessages) => {
                    const updated = [...prevMessages];
                    if (updated.length > 0) {
                      updated[updated.length - 1] = {
                        role: 'assistant',
                        content: assistantMessage,
                      };
                    }
                    return updated;
                  });
                }
              } catch (parseError) {
                console.error('Failed to parse final SSE event:', parseError);
              }
            }
          }
        } finally {
          reader.releaseLock();
        }

        // Mark streaming as complete
        setLoading(false);
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          // Request was cancelled, don't show error
          setLoading(false);
          return;
        }

        const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
        setError(errorMessage);
        setLoading(false);

        // Remove the placeholder assistant message on error
        setMessages((prevMessages) =>
          prevMessages.slice(0, -1)
        );
      }
    },
    [messages, conversationId, getToken, isSignedIn]
  );

  /**
   * Handle Enter key in input
   */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !loading) {
      e.preventDefault();
      handleSendMessage(input);
    }
  };

  /**
   * Start a new conversation
   */
  const handleNewConversation = () => {
    const newConversationId = generateUUID();
    setConversationId(newConversationId);
    setMessages([]);
    setInput('');
    setError(null);
  };

  /**
   * Retry sending a message after error
   */
  const handleRetry = () => {
    if (input.trim()) {
      handleSendMessage(input);
    } else if (messages.length > 0) {
      // If no input, retry the last user message
      const lastUserMessage = [...messages]
        .reverse()
        .find((msg) => msg.role === 'user');

      if (lastUserMessage) {
        // Remove failed assistant response if exists
        const lastAssistantIndex = messages.length - 1;
        const lastMessage = messages[lastAssistantIndex];
        if (lastMessage?.role === 'assistant') {
          setMessages(messages.slice(0, -1));
        }

        handleSendMessage(lastUserMessage.content);
      }
    }
  };

  /**
   * Cancel ongoing request
   */
  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  if (!isSignedIn) {
    return (
      <div className={styles.panel}>
        <div className={styles.header}>
          <h2 className={styles.title}>AI Chat</h2>
          <button
            className={styles.toggleButton}
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label="Toggle chat panel"
          >
            {isExpanded ? '−' : '+'}
          </button>
        </div>
        <div className={styles.content}>
          <div className={styles.signInPrompt}>
            <p>Please sign in to use the chat panel.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h2 className={styles.title}>AI Assistant</h2>
        <div className={styles.headerActions}>
          <button
            className={styles.newButton}
            onClick={handleNewConversation}
            title="Start a new conversation"
          >
            New
          </button>
          <button
            className={styles.toggleButton}
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label="Toggle chat panel"
          >
            {isExpanded ? '−' : '+'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <>
          <div className={styles.content}>
            <AIConsentBanner />
            <div className={styles.messages}>
              {messages.length === 0 ? (
                <div className={styles.emptyState}>
                  <p>Start a conversation by typing a message below.</p>
                </div>
              ) : (
                messages.map((msg, index) => (
                  <div key={index} className={`${styles.messageWrapper} ${styles[msg.role]}`}>
                    <div className={styles.messageBubble}>
                      <div className={styles.messageRole}>
                        {msg.role === 'user' ? '👤 You' : '🤖 Assistant'}
                      </div>
                      <div className={styles.messageContent}>
                        {msg.role === 'assistant' ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        ) : (
                          <p>{msg.content}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}

              {loading && (
                <div className={`${styles.messageWrapper} ${styles.assistant}`}>
                  <div className={styles.messageBubble}>
                    <div className={styles.messageRole}>🤖 Assistant</div>
                    <div className={styles.loadingIndicator}>
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {error && (
              <div className={styles.errorBanner}>
                <div className={styles.errorContent}>
                  <span>⚠️ Error: {error}</span>
                  <div className={styles.errorActions}>
                    <button className={styles.retryButton} onClick={handleRetry}>
                      Retry
                    </button>
                    <button className={styles.dismissButton} onClick={() => setError(null)}>
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className={styles.inputArea}>
            <div className={styles.inputWrapper}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your profile..."
                disabled={loading}
                className={styles.input}
              />
              {loading ? (
                <button className={styles.cancelButton} onClick={handleCancel}>
                  Cancel
                </button>
              ) : (
                <button
                  className={styles.sendButton}
                  onClick={() => handleSendMessage(input)}
                  disabled={!input.trim() || loading}
                >
                  Send
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ChatPanel;
