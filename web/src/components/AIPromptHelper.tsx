import { useState } from 'react';
import { ChevronDown, ChevronUp, Lightbulb, Copy, Check } from 'lucide-react';

interface AIPromptHelperProps {
  question: string;
  answer: string;
}

const PROMPT_RULES = `You will be provided with a single flashcard object containing a 'Question' and its correct 'Answer'. Your task is to generate four (4) incorrect distractor answers for this flashcard.

These distractors must strictly adhere to the following rules:

• Context-Dependent & Ambiguous in Isolation: Each distractor, when read on its own (without the associated 'Question'), should be ambiguous, incomplete, or not make full sense. It should only appear as a plausible (though incorrect) response when considered as an answer to the original 'Question' from the provided flashcard.

• No Hints or Question Referencing: Distractors must NOT contain any words, phrases, or concepts directly from the 'Question' that would give away the context or make the distractor obviously related to that specific question if seen in a list of other potential answers. The distractor should stand alone as a short phrase or term.

• Plausible but Definitely Incorrect: Distractors should be designed to seem like reasonable potential answers to the original 'Question'. However, each distractor must be clearly and definitively incorrect as an answer to the original 'Question'.

• Format & Style Consistency: Distractors must be in simple plaintext. Their style, length, and complexity should be similar to the provided correct 'Answer'. Avoid any special formatting, LaTeX, or complex mathematical notation.

• Uniqueness: Each generated distractor should be unique from the correct 'Answer' and from the other distractors you generate for the same question-answer pair.`;

export default function AIPromptHelper({ question, answer }: AIPromptHelperProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const getFullPrompt = () =>
    `${PROMPT_RULES}\n\nQuestion: ${question}\nAnswer: ${answer}`;

  const openInAI = (baseUrl: string) => {
    const url = `${baseUrl}${encodeURIComponent(getFullPrompt())}`;
    window.open(url, '_blank');
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(getFullPrompt());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const el = document.createElement('textarea');
      el.value = getFullPrompt();
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="rounded-xl bg-gray-50 overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-amber-500" />
          <span className="text-sm font-semibold text-purple-700">Human responses preferred!</span>
          <span className="text-sm text-gray-500">But if you need AI assistance...</span>
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>

      {isOpen && (
        <div className="px-4 pb-4 space-y-4">
          <p className="text-sm text-purple-700 font-medium">
            We strongly encourage human-generated distractors as they tend to be more effective and creative. However, if you need AI assistance, here&apos;s a suggested prompt:
          </p>

          <div className="rounded-xl bg-white p-4 space-y-2">
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wide">Suggested AI Prompt</p>
            <hr className="border-gray-100" />
            <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">{PROMPT_RULES}</pre>
            <hr className="border-gray-100" />
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wide">Your Flashcard Data:</p>
            <div className="bg-gray-50 rounded-lg p-2 font-mono text-xs text-gray-600">
              <span className="text-gray-400">Question:</span> {question || 'Your question will appear here'}<br />
              <span className="text-gray-400">Answer:</span> {answer || 'Your answer will appear here'}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => openInAI('https://chatgpt.com/?q=')}
              className="px-3 py-2.5 rounded-xl bg-emerald-50 text-emerald-700 hover:bg-emerald-100 text-sm font-semibold transition-colors"
            >
              Open in ChatGPT
            </button>
            <button
              type="button"
              onClick={() => openInAI('https://www.perplexity.ai/search?q=')}
              className="px-3 py-2.5 rounded-xl bg-sky-50 text-sky-700 hover:bg-sky-100 text-sm font-semibold transition-colors"
            >
              Open in Perplexity
            </button>
            <button
              type="button"
              onClick={() => openInAI('https://claude.ai/new?q=')}
              className="px-3 py-2.5 rounded-xl bg-amber-50 text-amber-700 hover:bg-amber-100 text-sm font-semibold transition-colors"
            >
              Open in Claude
            </button>
            <button
              type="button"
              onClick={handleCopy}
              className="px-3 py-2.5 rounded-xl bg-gray-100 text-gray-700 hover:bg-gray-200 text-sm font-semibold transition-colors flex items-center justify-center gap-1"
            >
              {copied ? (
                <><Check className="h-3.5 w-3.5 text-emerald-600" /> Copied!</>
              ) : (
                <><Copy className="h-3.5 w-3.5" /> Copy to Clipboard</>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
