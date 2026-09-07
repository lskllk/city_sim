/**
 * selectionStore —— 当前选中(只存 id; 一次只选中 NPC / Location / Entity 之一)。
 */
import { create } from 'zustand';

export type SelKind = 'npc' | 'location' | 'entity' | null;

interface SelectionState {
  kind: SelKind;
  selectedNpcId: string | null;
  selectedLocationId: string | null;
  selectedEntityId: string | null;
  selectedEventId: string | null;
  select: (kind: SelKind, id: string | null) => void;
  selectEvent: (id: string | null) => void;
  clearSelection: () => void;
}

export const useSelectionStore = create<SelectionState>()((set) => ({
  kind: null,
  selectedNpcId: null,
  selectedLocationId: null,
  selectedEntityId: null,
  selectedEventId: null,
  select: (kind, id) => {
    const out: Partial<SelectionState> = {
      kind, selectedNpcId: null, selectedLocationId: null,
      selectedEntityId: null,
    };
    if (kind === 'npc') out.selectedNpcId = id;
    else if (kind === 'location') out.selectedLocationId = id;
    else if (kind === 'entity') out.selectedEntityId = id;
    set(out as SelectionState);
  },
  selectEvent: (id) => set({ selectedEventId: id }),
  clearSelection: () => set({
    kind: null, selectedNpcId: null, selectedLocationId: null,
    selectedEntityId: null, selectedEventId: null,
  }),
}));
