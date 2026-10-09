import type { Component, InjectionKey } from 'vue';
import type { AulaAPI } from './api/client';

export type FeatureName = 'landing' | 'review' | 'editor' | 'export' | 'chat';
export type FeatureModules = Partial<Record<FeatureName, Component>>;

export interface LeaveProtection {
  hasChanges: () => boolean;
  confirmLeave: () => boolean;
}

export interface ShellServices {
  api: AulaAPI;
  features: FeatureModules;
  canApprove: boolean;
  leave: LeaveProtection;
  reviewNotes: Map<string, Record<string, string>>;
}

export const shellKey: InjectionKey<ShellServices> = Symbol('AulaLista shell');
