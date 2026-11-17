'use client';

import { useEffect, useState } from 'react';
import { SpinnerGap } from '@phosphor-icons/react';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  fetchGapQuestions,
  submitGapAnswers,
  type ForcedKeywordInput,
  type GapQuestion,
} from '@/lib/api/resume';
import { useTranslations } from '@/lib/i18n';

type Answer = 'have' | 'missing';
type Phase = 'loading' | 'answering' | 'saving' | 'done' | 'error';

interface GapInterviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  resumeId: string;
  jobId: string;
  /** Work the confirmed keywords into the preview (as attested skills). */
  onApplyConfirmed: (keywords: ForcedKeywordInput[]) => void;
  /** Keywords the user said they do not have, so the panel can hide them. */
  onDeclined: (keywords: string[]) => void;
  /** Another action (applying keywords) is running. */
  busy?: boolean;
}

/**
 * Ask about job keywords the master resume does not show. Only a "yes" answer
 * lets a keyword into the resume; a "no" answer is recorded and never applied.
 */
export function GapInterviewDialog({
  open,
  onOpenChange,
  resumeId,
  jobId,
  onApplyConfirmed,
  onDeclined,
  busy = false,
}: GapInterviewDialogProps) {
  const { t } = useTranslations();
  const [phase, setPhase] = useState<Phase>('loading');
  const [questions, setQuestions] = useState<GapQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const [declined, setDeclined] = useState<string[]>([]);
  const [error, setError] = useState<'load' | 'save' | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPhase('loading');
    setQuestions([]);
    setAnswers({});
    setConfirmed([]);
    setDeclined([]);
    setError(null);

    void (async () => {
      try {
        const next = await fetchGapQuestions(resumeId, jobId);
        if (cancelled) return;
        setQuestions(next);
        setPhase('answering');
      } catch (err) {
        if (cancelled) return;
        console.error(err);
        setError('load');
        setPhase('error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, resumeId, jobId]);

  const allAnswered = questions.every((question) => answers[question.keyword]);

  const save = async () => {
    setPhase('saving');
    setError(null);
    try {
      const result = await submitGapAnswers(
        resumeId,
        jobId,
        questions.map((question) => ({
          keyword: question.keyword,
          have_it: answers[question.keyword] === 'have',
        }))
      );
      const missing = questions
        .filter((question) => answers[question.keyword] !== 'have')
        .map((question) => question.keyword);
      setConfirmed(result.attested);
      setDeclined(missing);
      onDeclined(missing);
      setPhase('done');
    } catch (err) {
      console.error(err);
      setError('save');
      setPhase('answering');
    }
  };

  const applyConfirmed = () => {
    onApplyConfirmed(confirmed.map((keyword) => ({ keyword, attested: true })));
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{t('tailor.gapInterview.title')}</DialogTitle>
          <DialogDescription>{t('tailor.gapInterview.description')}</DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          {phase === 'loading' && (
            <p className="flex items-center gap-2 text-sm text-ink-soft">
              <SpinnerGap className="size-4 animate-spin" aria-hidden="true" />
              {t('tailor.gapInterview.loading')}
            </p>
          )}

          {phase !== 'loading' && questions.length === 0 && phase !== 'error' && (
            <p className="text-sm text-ink-soft">{t('tailor.gapInterview.empty')}</p>
          )}

          {questions.length > 0 && phase !== 'done' && (
            <ol className="space-y-3">
              {questions.map((question, index) => (
                <li key={question.keyword}>
                  <fieldset className="space-y-2 border border-ink/20 p-3">
                    <legend className="px-1 font-mono text-xs font-bold uppercase tracking-wider text-ink-soft">
                      {question.keyword}
                    </legend>
                    <p className="text-sm text-ink">{question.question}</p>
                    {question.context && (
                      <p className="text-xs text-ink-soft">{question.context}</p>
                    )}
                    <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:gap-6">
                      {(['have', 'missing'] as const).map((choice) => (
                        <label key={choice} className="flex items-center gap-2 text-sm text-ink">
                          <input
                            type="radio"
                            name={`gap-answer-${index}`}
                            checked={answers[question.keyword] === choice}
                            onChange={() =>
                              setAnswers((current) => ({
                                ...current,
                                [question.keyword]: choice,
                              }))
                            }
                            disabled={phase === 'saving'}
                            className="size-4 rounded-none border border-ink accent-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
                          />
                          {choice === 'have'
                            ? t('tailor.gapInterview.haveIt')
                            : t('tailor.gapInterview.doNotHaveIt')}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                </li>
              ))}
            </ol>
          )}

          {phase === 'done' && (
            <div className="space-y-4">
              {confirmed.length > 0 ? (
                <p className="text-sm text-ink">
                  {t('tailor.gapInterview.confirmed', { keywords: confirmed.join(', ') })}
                </p>
              ) : (
                <p className="text-sm text-ink-soft">{t('tailor.gapInterview.noneConfirmed')}</p>
              )}

              {declined.length > 0 && (
                <div className="space-y-1">
                  <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink-soft">
                    {t('tailor.gapInterview.studyTitle')}
                  </p>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-ink-soft">
                    {declined.map((keyword) => (
                      <li key={keyword}>
                        {t('tailor.gapInterview.studyRecommendation', { keyword })}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {error && (
            <Alert tone="error">
              {error === 'load'
                ? t('tailor.gapInterview.loadError')
                : t('tailor.gapInterview.saveError')}
            </Alert>
          )}
        </DialogBody>

        <DialogFooter>
          {phase === 'done' ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t('tailor.gapInterview.close')}
              </Button>
              {confirmed.length > 0 && (
                <Button onClick={applyConfirmed} disabled={busy}>
                  {busy ? (
                    <>
                      <SpinnerGap className="size-4 animate-spin" aria-hidden="true" />
                      {t('tailor.forceKeywords.applying')}
                    </>
                  ) : (
                    t('tailor.gapInterview.apply')
                  )}
                </Button>
              )}
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={() => void save()} disabled={phase !== 'answering' || !allAnswered}>
                {phase === 'saving' ? (
                  <>
                    <SpinnerGap className="size-4 animate-spin" aria-hidden="true" />
                    {t('tailor.gapInterview.saving')}
                  </>
                ) : (
                  t('tailor.gapInterview.save')
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
