/**
 * explain.test.ts —— UI 数据格式化纯函数测试(TASK004 #34)。
 * 重点: 空状态不出现 undefined/null/NaN; narrative/标题/图标不崩。
 */
import { describe, expect, it } from 'vitest';
import {
  actionVerb, narrative, needWord, orNa, signalZh, stateLabel,
} from './explain';

const resolve = (id: string): string => {
  const map: Record<string, string> = { market: '大超市', apple_1: '苹果' };
  return map[id] ?? id;
};

describe('narrative 空状态', () => {
  it('no intent/idle 且无信号知识 → 不出现 undefined', () => {
    const s = narrative({
      who: '王二', kind: 'idle', target: null, reason: null,
      relevantSignals: null, usedFacts: null, resolve,
    });
    expect(s).toContain('闲逛');
    expect(s).not.toMatch(/undefined|null|NaN/);
  });

  it('move_to 有信号无知识', () => {
    const s = narrative({
      who: '李四', kind: 'move_to', target: 'market', reason: '知识: 苹果能解饥饿 → 去 market',
      relevantSignals: [['hunger', 0.8]], usedFacts: [], resolve,
    });
    expect(s).toContain('前往');
    expect(s).toContain('大超市');
    expect(s).toContain('饥饿');
  });

  it('buy 有信号且有 used_fact → 提到知识', () => {
    const s = narrative({
      who: '王二', kind: 'buy', target: 'apple_1', reason: '购买 apple_1 解 hunger',
      relevantSignals: [['hunger', 0.9]],
      usedFacts: [{ subject: 'apple_1', relation: 'affords', obj: 'hunger' }],
      resolve,
    });
    expect(s).toContain('购买');
    expect(s).toContain('苹果');
    expect(s).toContain('知道');
  });
});

describe('orNa / needWord / 标签', () => {
  it('orNa 守卫 undefined/null/NaN', () => {
    expect(orNa(undefined)).toBe('—');
    expect(orNa(null)).toBe('—');
    expect(orNa(Number.NaN)).toBe('—');
    expect(orNa('ok')).toBe('ok');
  });

  it('needWord 分级', () => {
    expect(needWord(0.8)).toContain('高');
    expect(needWord(0.05)).toContain('低');
  });

  it('stateLabel/actionVerb 未知值不抛错', () => {
    expect(stateLabel(undefined, 'unknown-kind')).toBe('Idle');
    expect(actionVerb('whatever')).toBe('whatever');
    expect(signalZh('hp')).toBe('生命');
  });
});
