import { ref } from 'vue';

export function useDragDrop(onDropCallback?: (fromIndex: number, toIndex: number, data: Record<string, unknown>) => void) {
    const draggingIndex = ref<number | null>(null);
    const dragOverIndex = ref<number | null>(null);

    const onDragStart = (event: DragEvent, index: number, type: string = 'item') => {
        draggingIndex.value = index;
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.dropEffect = 'move';
            event.dataTransfer.setData('application/json', JSON.stringify({ type, index }));
            
            // Optional: Set drag image if target is provided
            const target = event.target as HTMLElement;
            const card = target.closest('.card') || target;
            if (card) {
                const rect = card.getBoundingClientRect();
                event.dataTransfer.setDragImage(card, event.clientX - rect.left, event.clientY - rect.top);
            }
        }
    };

    const onDragOver = (index: number) => {
        if (draggingIndex.value !== null) {
            dragOverIndex.value = index;
        }
    };

    const onDrop = (event: DragEvent, toIndex: number, type: string = 'item') => {
        if (!event.dataTransfer) return;
        const dataStr = event.dataTransfer.getData('application/json');
        if (!dataStr) return;
        const data = JSON.parse(dataStr);

        if (data.type !== type || data.index === toIndex) return;

        if (onDropCallback) {
            onDropCallback(data.index, toIndex, data);
        }
        
        draggingIndex.value = null;
        dragOverIndex.value = null;
    };

    const onDragEnd = () => {
        draggingIndex.value = null;
        dragOverIndex.value = null;
    };

    return {
        draggingIndex,
        dragOverIndex,
        onDragStart,
        onDragOver,
        onDrop,
        onDragEnd
    };
}