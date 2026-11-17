/**
 * Brazilian Portuguese date ranges for the print/PDF route.
 *
 * Stored date ranges are free text ("Jan 2021 - Present"). When the content
 * locale is `pt`, the print page rewrites the month names and the open-ended
 * status so the PDF reads as Brazilian Portuguese instead of English.
 */

import type { ResumeData } from '@/components/dashboard/resume-component';
import { formatDateRange } from '@/lib/utils';

const PT_MONTHS: Record<string, string> = {
  january: 'janeiro',
  february: 'fevereiro',
  march: 'março',
  april: 'abril',
  may: 'maio',
  june: 'junho',
  july: 'julho',
  august: 'agosto',
  september: 'setembro',
  october: 'outubro',
  november: 'novembro',
  december: 'dezembro',
  jan: 'jan',
  feb: 'fev',
  mar: 'mar',
  apr: 'abr',
  jun: 'jun',
  jul: 'jul',
  aug: 'ago',
  sep: 'set',
  sept: 'set',
  oct: 'out',
  nov: 'nov',
  dec: 'dez',
};

// Longest names first so "March" never matches as "Mar".
const MONTH_PATTERN = new RegExp(
  `\\b(?:${Object.keys(PT_MONTHS)
    .sort((a, b) => b.length - a.length)
    .join('|')})\\.?(?![A-Za-z])`,
  'gi'
);

const PRESENT_PATTERN = /\b(?:Present|Current|Now|Ongoing)\b/gi;

export const PT_BR_PRESENT = 'Atual';

/** Whether a locale code asks for Brazilian Portuguese formatting. */
export function isPortuguese(locale: string | null | undefined): boolean {
  return Boolean(locale && locale.toLowerCase().startsWith('pt'));
}

/** Translate the date words in an already-normalized range to Brazilian Portuguese. */
export function localizeDateRange(value: string, locale: string | null | undefined): string {
  if (!value || !isPortuguese(locale)) return value;
  return value
    .replace(MONTH_PATTERN, (match) => {
      const key = match.toLowerCase().replace(/\.$/, '');
      return PT_MONTHS[key] ?? match;
    })
    .replace(PRESENT_PATTERN, PT_BR_PRESENT);
}

/** `years` values are rendered as-is; localize them before the PDF templates run. */
function localizeYears<T extends { years?: string }>(entry: T, locale: string): T {
  if (!entry.years) return entry;
  const years = localizeDateRange(formatDateRange(entry.years), locale);
  return years === entry.years ? entry : { ...entry, years };
}

/**
 * Return a copy of the resume whose date ranges are in the content locale.
 *
 * Returns the same object when the locale is not `pt` so callers pay nothing.
 */
export function withLocalizedDateRanges(
  data: ResumeData,
  locale: string | null | undefined
): ResumeData {
  if (!isPortuguese(locale)) return data;
  const language = locale as string;

  const customSections = data.customSections
    ? Object.fromEntries(
        Object.entries(data.customSections).map(([key, section]) => [
          key,
          section.items?.length
            ? { ...section, items: section.items.map((item) => localizeYears(item, language)) }
            : section,
        ])
      )
    : data.customSections;

  return {
    ...data,
    workExperience: data.workExperience?.map((entry) => localizeYears(entry, language)),
    education: data.education?.map((entry) => localizeYears(entry, language)),
    personalProjects: data.personalProjects?.map((entry) => localizeYears(entry, language)),
    customSections,
  };
}
