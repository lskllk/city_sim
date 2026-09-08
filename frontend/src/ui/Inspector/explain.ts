/**
 * explain.ts —— 纯函数: 把 backend 结构化数据组织成可读的行为解释。
 * 只重组 backend 数据, 不重新计算 decision; 无 React/store 依赖(可单测)。
 */
export const SIGNAL_ZH: Record<string, string> = {
  energy: '精力', hunger: '饥饿', thirst: '口渴', bladder: '如厕',
  fun: '娱乐', hp: '生命',
};

export function signalZh(id: string): string {
  return SIGNAL_ZH[id] ?? id;
}

/** intent.kind → 中文动作 */
export const ACTION_ZH: Record<string, string> = {
  move_to: '前往', buy: '购买', interact: '使用', idle: '闲逛',
};

export const ACTION_ICON: Record<string, string> = {
  move_to: '🚶', buy: '🛒', interact: '🔧', idle: '😌',
};

export const KIND_EN: Record<string, string> = {
  move_to: 'Moving to', buy: 'Buying', interact: 'Using', idle: 'Idle',
};

export function actionVerb(kind: string): string {
  return ACTION_ZH[kind] ?? kind;
}

export function actionIcon(kind: string): string {
  return ACTION_ICON[kind] ?? '•';
}

/** 状态徽章(来自 act_class/active/travel 等既有字段, 不编造) */
export function stateLabel(actClass: string | undefined, kind: string): string {
  if (actClass === 'sleep') return '睡眠中';
  if (actClass === 'move') return '移动中';
  if (actClass === 'eat') return '进食中';
  if (actClass === 'toilet') return '如厕中';
  if (actClass === 'fun') return '娱乐中';
  if (actClass === 'drink') return '饮水';
  if (kind === 'buy') return '购买中';
  if (kind === 'move_to') return '移动中';
  if (kind === 'interact') return '交互中';
  return 'Idle';
}

/** deficit(need) → 文字等级 */
export function needWord(need: number): string {
  if (need >= 0.6) return '已经很高';
  if (need >= 0.3) return '正在上升';
  if (need >= 0.1) return '刚开始下降';
  return '还很低';
}

/**
 * 当前行为一句话(模板驱动, 全来自结构化字段)。
 */
export function narrative(opts: {
  who: string;
  kind: string;
  target: string | null;
  reason: string | null;
  relevantSignals: [string, number][] | null;
  usedFacts: Array<{ subject: string; relation: string; obj: unknown }> | null;
  resolve: (id: string) => string;
}): string {
  const { who, kind, target, reason } = opts;
  const resolve = opts.resolve ?? ((id: string): string => id);
  const sigs = opts.relevantSignals ?? [];
  const facts = opts.usedFacts ?? [];

  if (kind === 'idle') {
    const top = sigs.length > 0 ? sigs[0] : null;
    const why = top
      ? `，因为 ${signalZh(top[0])} ${needWord(top[1])}但仍不值得行动`
      : '';
    return `${who} 正在闲逛${why}。`;
  }

  const verb = actionVerb(kind);
  const t = target ? resolve(target) : '目标';
  const top = sigs.length > 0 ? sigs[0] : null;
  const sigClause = top ? `${signalZh(top[0])} ${needWord(top[1])}` : null;

  const knownFact = facts.length > 0
    ? `${resolve(facts[0].subject)} ${facts[0].relation} ${typeof facts[0].obj === 'string' ? facts[0].obj : String(facts[0].obj)}`
    : null;

  const parts = [`${who} 正在${verb} ${t}`];
  if (sigClause) parts.push(`因为${sigClause}`);
  if (knownFact) parts.push(`且知道「${knownFact}」`);
  if (reason && facts.length === 0 && !sigClause) parts.push(`原因: ${reason}`);
  return `${parts.join('；')}。`;
}

/** 行为区块(Current Behavior)标题与动词 */
export function behaviorTitle(kind: string, target: string | null,
                              resolve: (id: string) => string): string {
  const verb = KIND_EN[kind] ?? kind;
  return target ? `${verb} ${resolve(target)}` : verb;
}

/** 空状态文案(防 undefined/null/NaN 入 UI) */
export function orNa(v: unknown, fallback = '—'): string {
  if (v === undefined || v === null || Number.isNaN(v as number)) return fallback;
  return String(v);
}
