import { describe, it, expect, vi } from 'vitest';
import { useDragDrop } from '../composables/useDragDrop';

describe('useDragDrop', () => {
  it('sets dragging index on drag start', () => {
    const { draggingIndex, onDragStart } = useDragDrop();
    const mockEvent = {
      dataTransfer: {
        effectAllowed: '',
        dropEffect: '',
        setData: vi.fn(),
        setDragImage: vi.fn(),
      },
      target: document.createElement('div'),
      clientX: 0,
      clientY: 0,
    } as unknown as DragEvent;

    onDragStart(mockEvent, 5, 'test-item');
    expect(draggingIndex.value).toBe(5);
    expect(mockEvent.dataTransfer?.setData).toHaveBeenCalledWith(
      'application/json',
      JSON.stringify({ type: 'test-item', index: 5 })
    );
  });

  it('sets dragOver index', () => {
    const { draggingIndex, dragOverIndex, onDragOver } = useDragDrop();
    // Simulate start first
    draggingIndex.value = 1; 
    
    onDragOver(2);
    expect(dragOverIndex.value).toBe(2);
  });

  it('executes callback on valid drop', () => {
    const callback = vi.fn();
    const { onDrop } = useDragDrop(callback);
    
    const mockEvent = {
      dataTransfer: {
        getData: vi.fn().mockReturnValue(JSON.stringify({ type: 'item', index: 0 })),
      },
    } as unknown as DragEvent;

    // Drop on index 1
    onDrop(mockEvent, 1, 'item');
    
    expect(callback).toHaveBeenCalledWith(0, 1, expect.anything());
  });

  it('ignores drop if type mismatches', () => {
    const callback = vi.fn();
    const { onDrop } = useDragDrop(callback);
    
    const mockEvent = {
      dataTransfer: {
        getData: vi.fn().mockReturnValue(JSON.stringify({ type: 'other', index: 0 })),
      },
    } as unknown as DragEvent;

    onDrop(mockEvent, 1, 'item');
    expect(callback).not.toHaveBeenCalled();
  });
});