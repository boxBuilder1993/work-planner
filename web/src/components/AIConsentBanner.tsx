import { useState, useEffect } from 'react';
import styles from './AIConsentBanner.module.css';

/**
 * AI provider information from the backend
 */
interface AIStatus {
  model: string;
  is_local: boolean;
}

/**
 * Provider information extracted from model string
 */
interface ProviderInfo {
  name: string;
  color: string;
  icon: string;
}

/**
 * Extract provider name from model string
 * Examples:
 * - "claude-haiku-4-5" -> "Anthropic"
 * - "groq/llama-3.1-70b-versatile" -> "Groq"
 * - "together_ai/meta-llama/Llama-2-7b-hf" -> "Together AI"
 * - "ollama/llama2" -> "Ollama"
 */
function extractProvider(modelString: string): ProviderInfo {
  const lowerModel = modelString.toLowerCase();

  if (lowerModel.startsWith('claude')) {
    return { name: 'Anthropic', color: '#1B4D7A', icon: '🔐' };
  } else if (lowerModel.startsWith('groq')) {
    return { name: 'Groq', color: '#FF5C00', icon: '⚡' };
  } else if (lowerModel.startsWith('together')) {
    return { name: 'Together AI', color: '#8B5CF6', icon: '🤝' };
  } else if (lowerModel.startsWith('ollama')) {
    return { name: 'Ollama', color: '#6366F1', icon: '🏠' };
  }

  return { name: 'Unknown Provider', color: '#6B7280', icon: '🤖' };
}

/**
 * AIConsentBanner: Displays AI provider consent message on first use
 * - Fetches AI provider info from GET /api/ai/status
 * - Shows different messages for local vs cloud AI providers
 * - Persists dismissal state in localStorage
 * - Only displays once (unless localStorage is cleared)
 */
export const AIConsentBanner: React.FC = () => {
  const [isVisible, setIsVisible] = useState(false);
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const CONSENT_KEY = 'ai_chat_consent_shown';

  /**
   * Fetch AI status and check if consent has been shown before
   */
  useEffect(() => {
    const fetchAndCheck = async () => {
      try {
        // Check if user has already dismissed this banner
        const hasSeenConsent = localStorage.getItem(CONSENT_KEY);
        console.log('[AIConsentBanner] Checking localStorage for CONSENT_KEY:', CONSENT_KEY);
        console.log('[AIConsentBanner] hasSeenConsent value:', hasSeenConsent);
        if (hasSeenConsent) {
          console.log('[AIConsentBanner] User has already seen consent, returning early');
          setLoading(false);
          return;
        }

        // Fetch AI status
        console.log('[AIConsentBanner] Consent not shown before, fetching /api/ai/status');
        const response = await fetch('/api/ai/status');
        console.log('[AIConsentBanner] Fetch response status:', response.status, response.statusText);

        if (!response.ok) {
          throw new Error(`Failed to fetch AI status: ${response.statusText}`);
        }

        const data: AIStatus = await response.json();
        console.log('[AIConsentBanner] Successfully fetched AI status:', data);
        setAiStatus(data);
        console.log('[AIConsentBanner] Setting isVisible to true');
        setIsVisible(true);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to load AI status';
        console.error('[AIConsentBanner] Error in fetchAndCheck:', errorMessage);
        setError(errorMessage);
        // Still show error banner for visibility
        console.log('[AIConsentBanner] Setting isVisible to true (error state)');
        setIsVisible(true);
      } finally {
        console.log('[AIConsentBanner] Setting loading to false');
        setLoading(false);
      }
    };

    console.log('[AIConsentBanner] Component mounted, running fetchAndCheck');
    fetchAndCheck();
  }, []);

  /**
   * Handle dismissal of the banner
   */
  const handleDismiss = () => {
    localStorage.setItem(CONSENT_KEY, 'true');
    setIsVisible(false);
  };

  console.log('[AIConsentBanner] Render check - isVisible:', isVisible, 'loading:', loading, 'error:', error, 'aiStatus:', aiStatus);

  if (!isVisible || loading) {
    console.log('[AIConsentBanner] Returning null - isVisible:', isVisible, 'loading:', loading);
    return null;
  }

  // Error state
  if (error) {
    return (
      <div className={`${styles.banner} ${styles.error}`}>
        <div className={styles.content}>
          <div className={styles.errorIcon}>⚠️</div>
          <div className={styles.errorMessage}>
            <p className={styles.errorText}>{error}</p>
            <p className={styles.errorNote}>We could not load AI provider information.</p>
          </div>
        </div>
        <button className={styles.dismissButton} onClick={handleDismiss}>
          Dismiss
        </button>
      </div>
    );
  }

  // No AI status available
  if (!aiStatus) {
    return null;
  }

  const provider = extractProvider(aiStatus.model);
  const isLocal = aiStatus.is_local;
  console.log('[AIConsentBanner] Rendering banner - provider:', provider, 'isLocal:', isLocal);

  // Determine message and styling based on provider type
  let message: string;
  let messageDetails: string;
  let bannerClass = styles.banner;

  if (isLocal) {
    message = 'AI runs locally on this server';
    messageDetails = 'Your data does not leave this infrastructure.';
    bannerClass = `${styles.banner} ${styles.local}`;
  } else {
    message = `Your profile data is sent to ${provider.name}`;
    messageDetails =
      'to generate suggestions. It is not used for AI training. See privacy policy.';
    bannerClass = `${styles.banner} ${styles.cloud}`;
  }

  return (
    <div className={bannerClass}>
      <div className={styles.content}>
        <div className={styles.iconWrapper} style={{ color: provider.color }}>
          {provider.icon}
        </div>
        <div className={styles.messageWrapper}>
          <p className={styles.message}>{message}</p>
          <p className={styles.details}>{messageDetails}</p>
          {!isLocal && (
            <p className={styles.provider}>
              Provider: <strong>{provider.name}</strong>
            </p>
          )}
          {isLocal && (
            <p className={styles.model}>
              Model: <strong>{aiStatus.model}</strong>
            </p>
          )}
        </div>
      </div>
      <button className={styles.dismissButton} onClick={handleDismiss}>
        Got it
      </button>
    </div>
  );
};

export default AIConsentBanner;
