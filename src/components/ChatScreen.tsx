import React, { useState, useRef, useEffect } from 'react';
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
} from 'lucide-react';
import { AppView, ChatMessage, Artisan } from '../types';

interface ChatScreenProps {
  artisan: Artisan;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  setCurrentView: (view: AppView) => void;
}

export const ChatScreen: React.FC<ChatScreenProps> = ({
  artisan,
  messages,
  setMessages,
  setCurrentView,
}) => {
  const [inputText, setInputText] = useState('');
  const [devisAccepted, setDevisAccepted] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, devisAccepted, isTyping]);

  const handleSendMessage = () => {
    if (!inputText.trim()) return;

    const newMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'client',
      text: inputText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, newMsg]);
    setInputText('');

    // Simulate Artisan Response
    setIsTyping(true);
    setTimeout(() => {
      setIsTyping(false);
      setMessages((prev) => [
        ...prev,
        {
          id: `msg-artisan-${Date.now()}`,
          sender: 'artisan',
          text: 'Parfait ! Je peux intervenir dès cet après-midi vers 14h à votre adresse. Merci pour votre confiance.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    }, 2000);
  };

  const handleAcceptDevis = (_devisId: string) => {
    setDevisAccepted(true);
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.devis) {
          return {
            ...msg,
            devis: { ...msg.devis, status: 'accepted' },
          };
        }
        return msg;
      }),
    );

    // Auto-reply confirmation
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `msg-confirm-${Date.now()}`,
          sender: 'system',
          text: "✅ Devis de 12 000 FCFA accepté ! Le paiement sera bloqué en sécurité jusqu'à la fin des travaux.",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    }, 600);
  };

  return (
    <div className="bg-[#FAF7F2] text-[#1c1b1b] h-screen flex flex-col justify-between overflow-hidden">
      {/* Top Header */}
      <header className="flex justify-between items-center px-4 md:px-12 h-18 w-full z-40 bg-[#fcf9f8]/90 backdrop-blur-md border-b border-[#e5e2e1] shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCurrentView('client_home')}
            className="text-[#1c1b1b] p-2 hover:bg-[#f6f3f2] rounded-full transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-6 h-6" />
          </button>

          <div className="flex items-center gap-3">
            <div className="relative w-11 h-11">
              <img
                src={artisan.avatarUrl}
                alt={artisan.name}
                className="w-full h-full object-cover rounded-full border border-[#bfc9c1]"
              />
              <div className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 rounded-full border-2 border-[#fcf9f8]"></div>
            </div>

            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-base text-[#1c1b1b]">{artisan.name}</span>
                <span className="bg-[#abf2ca] text-[#002113] px-1.5 py-0.5 rounded-full text-[10px] font-sora font-bold flex items-center gap-0.5">
                  <BadgeCheck className="w-3 h-3" fill="currentColor" />
                  VÉRIFIÉ
                </span>
              </div>
              <span className="text-xs font-sora text-[#404943]">En ligne</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => alert(`Appel direct à ${artisan.name}: +221 77 000 00 00`)}
            className="text-[#004129] p-2 hover:bg-[#f6f3f2] rounded-full transition-colors cursor-pointer"
          >
            <Phone className="w-6 h-6" />
          </button>
          <button
            onClick={() => alert('Options de la conversation')}
            className="text-[#404943] p-2 hover:bg-[#f6f3f2] rounded-full transition-colors cursor-pointer"
          >
            <MoreVertical className="w-6 h-6" />
          </button>
        </div>
      </header>

      {/* Chat Messages Body */}
      <main className="flex-1 overflow-y-auto px-4 md:px-32 py-6 space-y-4">
        {/* Date Divider */}
        <div className="flex justify-center my-2">
          <span className="bg-[#eae7e7] px-3 py-1 rounded-full text-xs font-sora text-[#404943]">
            Aujourd&apos;hui
          </span>
        </div>

        {messages.map((msg) => {
          if (msg.sender === 'system') {
            return (
              <div key={msg.id} className="flex justify-center my-3">
                <span className="bg-[#abf2ca]/40 text-[#002113] border border-[#abf2ca] px-4 py-2 rounded-2xl text-xs font-sora font-medium text-center max-w-md shadow-sm">
                  {msg.text}
                </span>
              </div>
            );
          }

          if (msg.sender === 'artisan') {
            return (
              <div key={msg.id} className="flex flex-col items-start max-w-[88%] md:max-w-[70%]">
                {msg.text && (
                  <div className="bg-white p-4 rounded-2xl rounded-bl-sm text-[#1c1b1b] text-sm md:text-base leading-relaxed border border-[#e5e2e1] shadow-sm">
                    {msg.text}
                  </div>
                )}

                {/* Devis Card */}
                {msg.devis && (
                  <div className="devis-card bg-white rounded-2xl overflow-hidden flex flex-col w-full border-l-4 border-l-[#815600] my-2">
                    <div className="p-5 border-b border-[#f0eded]">
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <span className="text-[11px] font-sora text-[#815600] font-bold uppercase tracking-widest block mb-1">
                            PROPOSITION DE DEVIS
                          </span>
                          <h3 className="font-bold text-lg text-[#1c1b1b]">{msg.devis.title}</h3>
                        </div>
                        <FileText className="text-[#815600] w-9 h-9" />
                      </div>

                      <div className="space-y-2 mb-4 text-sm">
                        <div className="flex justify-between text-[#404943]">
                          <span>Main d&apos;œuvre</span>
                          <span className="font-semibold text-[#1c1b1b]">
                            {msg.devis.laborPrice.toLocaleString()} FCFA
                          </span>
                        </div>
                        <div className="flex justify-between text-[#404943]">
                          <span>Fournitures (Joints)</span>
                          <span className="font-semibold text-[#1c1b1b]">
                            {msg.devis.materialsPrice.toLocaleString()} FCFA
                          </span>
                        </div>
                      </div>

                      <div className="flex justify-between items-center bg-[#f6f3f2] p-3.5 rounded-xl">
                        <span className="font-sora text-sm font-bold text-[#1c1b1b]">Total</span>
                        <span className="font-bold text-xl text-[#004129]">
                          {msg.devis.totalPrice.toLocaleString()} FCFA
                        </span>
                      </div>
                    </div>

                    <div className="p-4 bg-[#fcf9f8]">
                      {devisAccepted || msg.devis.status === 'accepted' ? (
                        <div className="w-full bg-[#004129] text-white font-sora text-sm font-bold py-3 rounded-full flex items-center justify-center gap-2">
                          <span>Devis accepté</span>
                          <CheckCircle className="w-4 h-4" fill="currentColor" />
                        </div>
                      ) : (
                        <button
                          onClick={() => handleAcceptDevis(msg.devis!.id)}
                          className="w-full bg-[#815600] text-white font-sora text-sm font-bold py-3.5 rounded-full hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer shadow-md"
                        >
                          <span>Accepter le devis</span>
                          <CheckCircle className="w-4 h-4" />
                        </button>
                      )}

                      <p className="text-[11px] text-center text-[#707972] mt-2.5 italic font-sora">
                        Le paiement sera sécurisé par Téranga Services
                      </p>
                    </div>
                  </div>
                )}

                <span className="text-[11px] font-sora text-[#707972] mt-1 ml-1">
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
              <div className="bg-[#0e5a3c] p-4 rounded-2xl rounded-br-sm text-[#8acfa9] text-sm md:text-base leading-relaxed shadow-sm">
                {msg.text}
              </div>
              <div className="flex items-center gap-1 mt-1 mr-1">
                <span className="text-[11px] font-sora text-[#707972]">{msg.timestamp}</span>
                <CheckCheck className="w-4 h-4 text-[#004129]" />
              </div>
            </div>
          );
        })}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex items-center gap-2 text-[#707972] italic text-xs font-sora ml-2">
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 bg-[#707972] rounded-full animate-bounce"></div>
              <div className="w-1.5 h-1.5 bg-[#707972] rounded-full animate-bounce [animation-delay:0.2s]"></div>
              <div className="w-1.5 h-1.5 bg-[#707972] rounded-full animate-bounce [animation-delay:0.4s]"></div>
            </div>
            <span>{artisan.name} est en train d&apos;écrire...</span>
          </div>
        )}

        <div ref={chatEndRef} />
      </main>

      {/* Bottom Sticky Input */}
      <footer className="bg-[#fcf9f8]/95 backdrop-blur-md border-t border-[#e5e2e1] px-4 md:px-12 py-3 flex items-center gap-3 shrink-0 pb-safe z-30">
        <button
          onClick={() => alert('Joindre une photo ou un document')}
          className="w-10 h-10 flex items-center justify-center text-[#707972] hover:bg-[#f6f3f2] rounded-full transition-colors shrink-0 cursor-pointer"
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
            className="w-full bg-[#f6f3f2] border-none rounded-full px-5 py-3 text-sm md:text-base text-[#1c1b1b] focus:ring-1 focus:ring-[#004129] placeholder:text-[#707972] outline-none"
          />
          <button
            onClick={() => setInputText((prev) => prev + ' 😊')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-[#707972] hover:text-[#004129]"
          >
            <Smile className="w-5 h-5" />
          </button>
        </div>

        <button
          onClick={handleSendMessage}
          className="w-11 h-11 bg-[#0e5a3c] text-[#8acfa9] rounded-full flex items-center justify-center shadow-md active:scale-90 transition-transform shrink-0 cursor-pointer"
        >
          <Send className="w-5 h-5" fill="currentColor" />
        </button>
      </footer>
    </div>
  );
};
