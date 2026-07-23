import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  BadgeCheck,
  Phone,
  MoreVertical,
  FileText,
  CheckCircle,
  CheckCheck,
  PlusCircle,
  Smile,
  Send,
  MessageCircle,
} from 'lucide-react';
import { Link, useParams } from 'react-router';
import { SafeImage } from '../../components/ui/SafeImage';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { useArtisan } from '../artisans/hooks/useArtisan';
import { useChat } from './hooks/useChat';

export const ChatScreen: React.FC = () => {
  const { conversationId = '' } = useParams<{ conversationId: string }>();
  const { data: artisan, isLoading: isArtisanLoading, error: artisanError, reload: reloadArtisan } =
    useArtisan(conversationId);
  const {
    data: messages,
    isLoading: isMessagesLoading,
    error: messagesError,
    reload: reloadMessages,
    sendMessage,
    acceptDevis,
  } = useChat(conversationId);

  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;
    const text = inputText;
    setInputText('');
    setIsTyping(true);
    try {
      await sendMessage(text);
    } finally {
      setIsTyping(false);
    }
  };

  const isInitialLoading = (isArtisanLoading && !artisan) || (isMessagesLoading && !messages);
  const hasBlockingError = (artisanError && !artisan) || (messagesError && !messages);

  return (
    <div className="bg-background-alt text-foreground h-screen flex flex-col justify-between overflow-hidden">
      {/* Top Header */}
      <header className="flex justify-between items-center px-4 md:px-12 h-18 w-full z-40 bg-background/90 backdrop-blur-md border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <Link
            to="/accueil"
            className="text-foreground p-2 hover:bg-surface-muted rounded-full transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-6 h-6" />
          </Link>

          {artisan ? (
            <div className="flex items-center gap-3">
              <div className="relative w-11 h-11">
                <SafeImage
                  src={artisan.avatarUrl}
                  fallback="/images/placeholder-avatar.svg"
                  alt={artisan.name}
                  className="w-full h-full object-cover rounded-full border border-border-strong"
                />
                <div className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 rounded-full border-2 border-background"></div>
              </div>

              <div className="flex flex-col">
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-base text-foreground">{artisan.name}</span>
                  <span className="bg-success text-success-foreground px-1.5 py-0.5 rounded-full text-[10px] font-sora font-bold flex items-center gap-0.5">
                    <BadgeCheck className="w-3 h-3" fill="currentColor" />
                    VÉRIFIÉ
                  </span>
                </div>
                <span className="text-xs font-sora text-muted-foreground">En ligne</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Skeleton className="w-11 h-11 rounded-full" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-16" />
              </div>
            </div>
          )}
        </div>

        {artisan && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => alert(`Appel direct à ${artisan.name}: +221 77 000 00 00`)}
              className="text-primary p-2 hover:bg-surface-muted rounded-full transition-colors cursor-pointer"
            >
              <Phone className="w-6 h-6" />
            </button>
            <button
              onClick={() => alert('Options de la conversation')}
              className="text-muted-foreground p-2 hover:bg-surface-muted rounded-full transition-colors cursor-pointer"
            >
              <MoreVertical className="w-6 h-6" />
            </button>
          </div>
        )}
      </header>

      {/* Chat Messages Body */}
      <main className="flex-1 overflow-y-auto px-4 md:px-32 py-6 space-y-4">
        {isInitialLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-16 w-2/3 rounded-2xl" />
            <Skeleton className="h-24 w-4/5 rounded-2xl" />
            <Skeleton className="h-12 w-1/2 rounded-2xl ml-auto" />
          </div>
        ) : hasBlockingError ? (
          <ErrorState
            message={(artisanError ?? messagesError)?.message ?? 'Une erreur est survenue.'}
            onRetry={() => {
              reloadArtisan();
              reloadMessages();
            }}
          />
        ) : (
          <>
            {/* Date Divider */}
            <div className="flex justify-center my-2">
              <span className="bg-border-subtle px-3 py-1 rounded-full text-xs font-sora text-muted-foreground">
                Aujourd&apos;hui
              </span>
            </div>

            {messages && messages.length === 0 ? (
              <EmptyState
                icon={<MessageCircle className="text-muted-foreground-soft mb-2 w-9 h-9 mx-auto" />}
                title="Aucun message pour l'instant."
                description="Envoyez le premier message pour démarrer la conversation."
              />
            ) : (
              (messages ?? []).map((msg) => {
                if (msg.sender === 'system') {
                  return (
                    <div key={msg.id} className="flex justify-center my-3">
                      <span className="bg-success/40 text-success-foreground border border-success px-4 py-2 rounded-2xl text-xs font-sora font-medium text-center max-w-md shadow-sm">
                        {msg.text}
                      </span>
                    </div>
                  );
                }

                if (msg.sender === 'artisan') {
                  return (
                    <div key={msg.id} className="flex flex-col items-start max-w-[88%] md:max-w-[70%]">
                      {msg.text && (
                        <div className="bg-white p-4 rounded-2xl rounded-bl-sm text-foreground text-sm md:text-base leading-relaxed border border-border shadow-sm">
                          {msg.text}
                        </div>
                      )}

                      {/* Devis Card */}
                      {msg.devis && (
                        <div className="devis-card bg-white rounded-2xl overflow-hidden flex flex-col w-full border-l-4 border-l-accent-foreground my-2">
                          <div className="p-5 border-b border-border-faint">
                            <div className="flex justify-between items-start mb-4">
                              <div>
                                <span className="text-[11px] font-sora text-accent-foreground font-bold uppercase tracking-widest block mb-1">
                                  PROPOSITION DE DEVIS
                                </span>
                                <h3 className="font-bold text-lg text-foreground">{msg.devis.title}</h3>
                              </div>
                              <FileText className="text-accent-foreground w-9 h-9" />
                            </div>

                            <div className="space-y-2 mb-4 text-sm">
                              <div className="flex justify-between text-muted-foreground">
                                <span>Main d&apos;œuvre</span>
                                <span className="font-semibold text-foreground">
                                  {msg.devis.laborPrice.toLocaleString()} FCFA
                                </span>
                              </div>
                              <div className="flex justify-between text-muted-foreground">
                                <span>Fournitures (Joints)</span>
                                <span className="font-semibold text-foreground">
                                  {msg.devis.materialsPrice.toLocaleString()} FCFA
                                </span>
                              </div>
                            </div>

                            <div className="flex justify-between items-center bg-surface-muted p-3.5 rounded-xl">
                              <span className="font-sora text-sm font-bold text-foreground">Total</span>
                              <span className="font-bold text-xl text-primary">
                                {msg.devis.totalPrice.toLocaleString()} FCFA
                              </span>
                            </div>
                          </div>

                          <div className="p-4 bg-background">
                            {msg.devis.status === 'accepted' ? (
                              <div className="w-full bg-primary text-white font-sora text-sm font-bold py-3 rounded-full flex items-center justify-center gap-2">
                                <span>Devis accepté</span>
                                <CheckCircle className="w-4 h-4" fill="currentColor" />
                              </div>
                            ) : (
                              <button
                                onClick={() => acceptDevis()}
                                className="w-full bg-accent-foreground text-white font-sora text-sm font-bold py-3.5 rounded-full hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer shadow-md"
                              >
                                <span>Accepter le devis</span>
                                <CheckCircle className="w-4 h-4" />
                              </button>
                            )}

                            <p className="text-[11px] text-center text-muted-foreground-soft mt-2.5 italic font-sora">
                              Le paiement sera sécurisé par Téranga Services
                            </p>
                          </div>
                        </div>
                      )}

                      <span className="text-[11px] font-sora text-muted-foreground-soft mt-1 ml-1">
                        {msg.timestamp}
                      </span>
                    </div>
                  );
                }

                // Client message
                return (
                  <div
                    key={msg.id}
                    className="flex flex-col items-end self-end max-w-[88%] md:max-w-[70%]"
                  >
                    <div className="bg-primary-emerald p-4 rounded-2xl rounded-br-sm text-primary-emerald-foreground text-sm md:text-base leading-relaxed shadow-sm">
                      {msg.text}
                    </div>
                    <div className="flex items-center gap-1 mt-1 mr-1">
                      <span className="text-[11px] font-sora text-muted-foreground-soft">
                        {msg.timestamp}
                      </span>
                      <CheckCheck className="w-4 h-4 text-primary" />
                    </div>
                  </div>
                );
              })
            )}

            {/* Typing indicator */}
            {isTyping && (
              <div className="flex items-center gap-2 text-muted-foreground-soft italic text-xs font-sora ml-2">
                <div className="flex gap-1">
                  <div className="w-1.5 h-1.5 bg-muted-foreground-soft rounded-full animate-bounce"></div>
                  <div className="w-1.5 h-1.5 bg-muted-foreground-soft rounded-full animate-bounce [animation-delay:0.2s]"></div>
                  <div className="w-1.5 h-1.5 bg-muted-foreground-soft rounded-full animate-bounce [animation-delay:0.4s]"></div>
                </div>
                <span>{artisan?.name} est en train d&apos;écrire...</span>
              </div>
            )}
          </>
        )}

        <div ref={chatEndRef} />
      </main>

      {/* Bottom Sticky Input */}
      <footer className="bg-background/95 backdrop-blur-md border-t border-border px-4 md:px-12 py-3 flex items-center gap-3 shrink-0 pb-safe z-30">
        <button
          onClick={() => alert('Joindre une photo ou un document')}
          className="w-10 h-10 flex items-center justify-center text-muted-foreground-soft hover:bg-surface-muted rounded-full transition-colors shrink-0 cursor-pointer"
        >
          <PlusCircle className="w-6 h-6" />
        </button>

        <div className="flex-1 relative">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder="Votre message..."
            className="w-full bg-surface-muted border-none rounded-full px-5 py-3 text-sm md:text-base text-foreground focus:ring-1 focus:ring-primary placeholder:text-muted-foreground-soft outline-none"
          />
          <button
            onClick={() => setInputText((prev) => prev + ' 😊')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground-soft hover:text-primary"
          >
            <Smile className="w-5 h-5" />
          </button>
        </div>

        <button
          onClick={handleSendMessage}
          className="w-11 h-11 bg-primary-emerald text-primary-emerald-foreground rounded-full flex items-center justify-center shadow-md active:scale-90 transition-transform shrink-0 cursor-pointer"
        >
          <Send className="w-5 h-5" fill="currentColor" />
        </button>
      </footer>
    </div>
  );
};
