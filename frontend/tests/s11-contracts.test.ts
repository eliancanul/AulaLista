import { describe, expect, it } from 'vitest';
import { decodeDraft, decodeInterpretation, toSavedActivity } from '../src/contracts/interpretation';
import { interpretation } from './s11-fixtures';

describe('published data projections', () => {
  it('keeps the unknown school level and returns detached data', () => {
    const source = interpretation();
    const result = decodeInterpretation(source);
    expect(result.fields[1]).toEqual({ key: 'nivel_educativo', value: null, status: 'unknown', evidence_ids: [], reason: 'No está indicado.' });
    result.draft.title = 'Changed';
    expect(source.draft.title).toBe('Figuras');
  });

  it('rejects missing references and unsupported extracted claims', () => {
    const bad = interpretation();
    bad.fields[0].evidence_ids = ['absent'];
    expect(() => decodeInterpretation(bad)).toThrow();
    bad.fields[0].evidence_ids = [];
    expect(() => decodeInterpretation(bad)).toThrow();
    bad.fields[0].status = 'unknown';
    expect(() => decodeInterpretation(bad)).toThrow();
  });

  it('rejects invalid revisions and malformed activity arrays', () => {
    expect(() => decodeDraft({ ...interpretation().draft, revision: 0 })).toThrow();
    expect(() => decodeDraft({ ...interpretation().draft, steps: 'texto' })).toThrow();
  });

  it('keeps exact teacher text and only projects approval confirmed in a persisted response', () => {
    const draft = interpretation().draft;
    draft.title = '  Texto\n';
    const pending = toSavedActivity(draft);
    expect(pending.content.title).toBe('  Texto\n');
    expect(pending.status).toBe('draft');
    expect(pending.approved).toBeNull();
    const approved = toSavedActivity({ ...draft, revision: 2, approval_status: 'approved' });
    const edited = toSavedActivity({ ...draft, revision: 3, title: 'Nueva edición' }, approved.approved);
    expect(edited.status).toBe('draft');
    expect(edited.approved?.content.title).toBe('  Texto\n');
    expect(edited.approved?.revision).toBe(2);
    edited.content.steps.push('Nuevo');
    expect(edited.approved?.content.steps).toEqual(['Comparar.']);
  });
});
