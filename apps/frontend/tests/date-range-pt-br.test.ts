import { describe, expect, it } from 'vitest';
import { isPortuguese, localizeDateRange, withLocalizedDateRanges } from '@/lib/utils/date-range';
import type { ResumeData } from '@/components/dashboard/resume-component';

describe('localizeDateRange', () => {
  it('translates English months and the open-ended status to Brazilian Portuguese', () => {
    expect(localizeDateRange('Jan 2021 - Present', 'pt')).toBe('jan 2021 - Atual');
    expect(localizeDateRange('January 2021 - December 2024', 'pt')).toBe(
      'janeiro 2021 - dezembro 2024'
    );
    expect(localizeDateRange('Sept 2020 - Oct 2021', 'pt')).toBe('set 2020 - out 2021');
  });

  it('keeps numeric ranges untouched', () => {
    expect(localizeDateRange('2023 - 2025', 'pt')).toBe('2023 - 2025');
  });

  it('does nothing for other locales', () => {
    expect(localizeDateRange('Jan 2021 - Present', 'en')).toBe('Jan 2021 - Present');
    expect(localizeDateRange('Jan 2021 - Present', null)).toBe('Jan 2021 - Present');
  });

  it('recognizes pt and pt-BR', () => {
    expect(isPortuguese('pt')).toBe(true);
    expect(isPortuguese('pt-BR')).toBe(true);
    expect(isPortuguese('en')).toBe(false);
  });
});

describe('withLocalizedDateRanges', () => {
  const data = {
    personalInfo: { name: 'Ada' },
    summary: '',
    workExperience: [
      { id: 1, title: 'Dev', company: 'Acme', years: 'Jan 2021 - Present' },
      { id: 2, title: 'Intern', company: 'Acme', years: '2022 2023' },
    ],
    education: [{ id: 1, institution: 'USP', degree: 'BSc', years: 'Mar 2014 - Dec 2018' }],
    personalProjects: [{ id: 1, name: 'Site', years: 'Jun 2024 Present' }],
    customSections: {
      custom_1: {
        sectionType: 'itemList',
        items: [{ id: 1, title: 'Volunteer', years: 'Jan 2020 - Present' }],
      },
    },
  } as unknown as ResumeData;

  it('rewrites every date range when the content locale is pt', () => {
    const result = withLocalizedDateRanges(data, 'pt');

    expect(result.workExperience?.map((entry) => entry.years)).toEqual([
      'jan 2021 - Atual',
      '2022 - 2023',
    ]);
    expect(result.education?.[0].years).toBe('mar 2014 - dez 2018');
    expect(result.personalProjects?.[0].years).toBe('jun 2024 - Atual');
    expect(result.customSections?.custom_1.items?.[0].years).toBe('jan 2020 - Atual');
    // The original object is never mutated.
    expect(data.workExperience?.[0].years).toBe('Jan 2021 - Present');
  });

  it('returns the same object for other locales', () => {
    expect(withLocalizedDateRanges(data, 'en')).toBe(data);
  });
});
