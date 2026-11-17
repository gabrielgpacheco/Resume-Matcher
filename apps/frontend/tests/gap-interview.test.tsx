import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { KeywordForcingPanel } from '@/components/tailor/keyword-forcing-panel';

vi.mock('@/lib/i18n', () => ({
  useTranslations: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
  }),
}));

const api = vi.hoisted(() => ({
  fetchGapQuestions: vi.fn(),
  submitGapAnswers: vi.fn(),
}));

vi.mock('@/lib/api/resume', () => api);

const QUESTIONS = [
  {
    keyword: 'Kubernetes',
    question: 'Have you used Kubernetes?',
    context: 'The posting runs a Kubernetes platform.',
  },
  { keyword: 'Terraform', question: 'Have you used Terraform?', context: '' },
];

function renderPanel(onApply = vi.fn()) {
  render(
    <KeywordForcingPanel
      unsupported={['Kubernetes', 'Terraform']}
      supported={[]}
      onApply={onApply}
      resumeId="resume-1"
      jobId="job-1"
    />
  );
  return onApply;
}

function openDialog() {
  fireEvent.click(screen.getByRole('button', { name: 'tailor.gapInterview.open' }));
}

async function openInterview() {
  openDialog();
  await screen.findByText('Have you used Kubernetes?');
}

describe('KeywordForcingPanel gap interview', () => {
  beforeEach(() => {
    api.fetchGapQuestions.mockReset();
    api.submitGapAnswers.mockReset();
  });

  it('does not offer the interview without a resume and job', () => {
    render(<KeywordForcingPanel unsupported={['Kubernetes']} supported={[]} onApply={vi.fn()} />);
    expect(
      screen.queryByRole('button', { name: 'tailor.gapInterview.open' })
    ).not.toBeInTheDocument();
  });

  it('records the answers and applies only the confirmed keywords', async () => {
    api.fetchGapQuestions.mockResolvedValue(QUESTIONS);
    api.submitGapAnswers.mockResolvedValue({
      results: [
        { keyword: 'Kubernetes', have_it: true },
        { keyword: 'Terraform', have_it: false },
      ],
      attested: ['Kubernetes'],
    });
    const onApply = renderPanel();

    await openInterview();
    const groups = screen.getAllByRole('group');
    fireEvent.click(within(groups[0]).getByLabelText('tailor.gapInterview.haveIt'));
    fireEvent.click(within(groups[1]).getByLabelText('tailor.gapInterview.doNotHaveIt'));
    fireEvent.click(screen.getByRole('button', { name: 'tailor.gapInterview.save' }));

    await screen.findByText(/tailor\.gapInterview\.confirmed/);
    expect(api.submitGapAnswers).toHaveBeenCalledWith('resume-1', 'job-1', [
      { keyword: 'Kubernetes', have_it: true },
      { keyword: 'Terraform', have_it: false },
    ]);
    // A "no" answer produces a study suggestion, never resume content.
    expect(screen.getByText(/studyRecommendation.*Terraform/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'tailor.gapInterview.apply' }));

    expect(onApply).toHaveBeenCalledWith([{ keyword: 'Kubernetes', attested: true }], true);
    // The declined keyword is out of the picker until the preview changes.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Terraform/ })).not.toBeInTheDocument()
    );
  });

  it('keeps saving disabled until every question is answered', async () => {
    api.fetchGapQuestions.mockResolvedValue(QUESTIONS);
    renderPanel();

    await openInterview();
    const save = screen.getByRole('button', { name: 'tailor.gapInterview.save' });
    expect(save).toBeDisabled();

    const groups = screen.getAllByRole('group');
    fireEvent.click(within(groups[0]).getByLabelText('tailor.gapInterview.doNotHaveIt'));
    expect(save).toBeDisabled();

    fireEvent.click(within(groups[1]).getByLabelText('tailor.gapInterview.doNotHaveIt'));
    expect(save).toBeEnabled();
  });

  it('explains when there is nothing to ask', async () => {
    api.fetchGapQuestions.mockResolvedValue([]);
    renderPanel();

    openDialog();
    expect(await screen.findByText('tailor.gapInterview.empty')).toBeInTheDocument();
  });

  it('shows a retryable error when the questions cannot be loaded', async () => {
    api.fetchGapQuestions.mockRejectedValue(new Error('boom'));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderPanel();

    openDialog();
    expect(await screen.findByText('tailor.gapInterview.loadError')).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
