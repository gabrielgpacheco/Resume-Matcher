'use client';

import { useState } from 'react';
import { SpinnerGap } from '@phosphor-icons/react';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { GapInterviewDialog } from '@/components/tailor/gap-interview-dialog';
import type { ForcedKeywordInput } from '@/lib/api/resume';
import { useTranslations } from '@/lib/i18n';
import { cn } from '@/lib/utils';

/** Keywords one preview can carry; matches the confirm request's limit. */
export const MAX_FORCED_KEYWORDS = 30;

interface KeywordForcingPanelProps {
  /** Job keywords the master resume does not show: need "I have this". */
  unsupported: string[];
  /** Job keywords the master shows but the tailored resume does not use yet. */
  supported: string[];
  onApply: (keywords: ForcedKeywordInput[], addToMaster: boolean) => void;
  busy?: boolean;
  error?: string | null;
  /** How many more keywords this preview may take (the server keeps at most 30). */
  remaining?: number;
  /** Source resume and job: enable the gap interview when both are known. */
  resumeId?: string;
  jobId?: string;
}

function Chip({
  keyword,
  selected,
  disabled,
  onToggle,
  actionLabel,
}: {
  keyword: string;
  selected: boolean;
  disabled: boolean;
  onToggle: () => void;
  actionLabel: string;
}) {
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        disabled={disabled}
        onClick={onToggle}
        className={cn(
          'flex items-center gap-2 border border-ink px-2 py-1 font-mono text-xs transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas',
          'disabled:cursor-not-allowed disabled:opacity-50',
          selected ? 'bg-ink text-white' : 'bg-white text-ink hover:bg-panel'
        )}
      >
        <span>{keyword}</span>
        <span className={cn('uppercase tracking-wider', selected ? 'text-white' : 'text-ink-soft')}>
          {actionLabel}
        </span>
      </button>
    </li>
  );
}

/**
 * Pick missing job keywords to work into the preview. Keywords the master does
 * not show are applied only after the user says "I have this".
 */
export function KeywordForcingPanel({
  unsupported,
  supported,
  onApply,
  busy = false,
  error,
  remaining = MAX_FORCED_KEYWORDS,
  resumeId,
  jobId,
}: KeywordForcingPanelProps) {
  const { t } = useTranslations();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [addToMaster, setAddToMaster] = useState(true);
  const [interviewOpen, setInterviewOpen] = useState(false);
  // Keywords the interview answered "no" to: hidden until the preview changes.
  const [declined, setDeclined] = useState<Set<string>>(new Set());

  const unsupportedList = unsupported.filter((keyword) => !declined.has(keyword));

  // Keep the panel mounted while the interview result is showing.
  if (unsupportedList.length === 0 && supported.length === 0 && !interviewOpen) return null;

  const toggle = (keyword: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(keyword)) next.delete(keyword);
      else next.add(keyword);
      return next;
    });

  const unsupportedSet = new Set(unsupported);
  const full = selected.size >= remaining;
  const anyAttested = [...selected].some((k) => unsupportedSet.has(k));
  const canInterview = Boolean(resumeId && jobId) && unsupportedList.length > 0;

  const apply = () => {
    const keywords = [...selected].map((keyword) => ({
      keyword,
      attested: unsupportedSet.has(keyword),
    }));
    onApply(keywords, anyAttested && addToMaster);
    setSelected(new Set());
  };

  return (
    <section
      aria-labelledby="keyword-forcing-heading"
      className="space-y-4 border-2 border-ink bg-white p-4"
    >
      <div>
        <h3
          id="keyword-forcing-heading"
          className="font-mono text-sm font-bold uppercase tracking-wider text-ink"
        >
          {t('tailor.forceKeywords.title')}
        </h3>
        <p className="mt-1 text-sm text-ink-soft">{t('tailor.forceKeywords.description')}</p>
        {canInterview && resumeId && jobId && (
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => setInterviewOpen(true)}
            disabled={busy}
          >
            {t('tailor.gapInterview.open')}
          </Button>
        )}
      </div>

      {supported.length > 0 && (
        <div>
          <p className="mb-2 font-mono text-xs font-bold uppercase tracking-wider text-ink-soft">
            {t('tailor.forceKeywords.supported')}
          </p>
          <ul className="flex flex-wrap gap-2">
            {supported.map((keyword) => (
              <Chip
                key={keyword}
                keyword={keyword}
                selected={selected.has(keyword)}
                disabled={busy || (full && !selected.has(keyword))}
                onToggle={() => toggle(keyword)}
                actionLabel={t('tailor.forceKeywords.apply')}
              />
            ))}
          </ul>
        </div>
      )}

      {unsupportedList.length > 0 && (
        <div>
          <p className="mb-2 font-mono text-xs font-bold uppercase tracking-wider text-ink-soft">
            {t('tailor.forceKeywords.unsupported')}
          </p>
          <ul className="flex flex-wrap gap-2">
            {unsupportedList.map((keyword) => (
              <Chip
                key={keyword}
                keyword={keyword}
                selected={selected.has(keyword)}
                disabled={busy || (full && !selected.has(keyword))}
                onToggle={() => toggle(keyword)}
                actionLabel={t('tailor.forceKeywords.haveThis')}
              />
            ))}
          </ul>
          <p className="mt-2 text-sm text-ink-soft">{t('tailor.forceKeywords.attestNote')}</p>
        </div>
      )}

      {anyAttested && (
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={addToMaster}
            onChange={(event) => setAddToMaster(event.target.checked)}
            disabled={busy}
            className="size-4 rounded-none border border-ink accent-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
          />
          {t('tailor.forceKeywords.addToMaster')}
        </label>
      )}

      {full && (
        <p className="text-sm text-ink-soft">
          {t('tailor.forceKeywords.limitReached', { max: MAX_FORCED_KEYWORDS })}
        </p>
      )}

      {error && <Alert tone="error">{error}</Alert>}

      <Button onClick={apply} disabled={busy || selected.size === 0}>
        {busy ? (
          <>
            <SpinnerGap className="size-4 animate-spin" aria-hidden="true" />
            {t('tailor.forceKeywords.applying')}
          </>
        ) : (
          t('tailor.forceKeywords.applyButton', { count: selected.size })
        )}
      </Button>

      {resumeId && jobId && (
        <GapInterviewDialog
          open={interviewOpen}
          onOpenChange={setInterviewOpen}
          resumeId={resumeId}
          jobId={jobId}
          busy={busy}
          onApplyConfirmed={(keywords) => onApply(keywords, true)}
          onDeclined={(keywords) => setDeclined((current) => new Set([...current, ...keywords]))}
        />
      )}
    </section>
  );
}
