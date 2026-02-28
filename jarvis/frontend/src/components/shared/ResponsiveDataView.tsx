import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from './MobileCardList'

interface ResponsiveDataViewProps<T> {
  data: T[]
  mobileFields: MobileCardField<T>[]
  getRowId: (row: T) => number
  onRowClick?: (row: T) => void
  selectable?: boolean
  selectedIds?: Set<number> | number[]
  onToggleSelect?: (id: number) => void
  actions?: (row: T) => React.ReactNode
  emptyMessage?: string
  isLoading?: boolean
  /** Desktop table — pass the full table JSX */
  desktopTable: React.ReactNode
}

/**
 * Renders a full table on desktop and a card list on mobile.
 * The desktop table is passed as-is (each page controls its own table layout).
 */
export function ResponsiveDataView<T>({
  data,
  mobileFields,
  getRowId,
  onRowClick,
  selectable,
  selectedIds,
  onToggleSelect,
  actions,
  emptyMessage,
  isLoading,
  desktopTable,
}: ResponsiveDataViewProps<T>) {
  const isMobile = useIsMobile()

  if (isMobile) {
    return (
      <MobileCardList
        data={data}
        fields={mobileFields}
        getRowId={getRowId}
        onRowClick={onRowClick}
        selectable={selectable}
        selectedIds={selectedIds}
        onToggleSelect={onToggleSelect}
        actions={actions}
        emptyMessage={emptyMessage}
        isLoading={isLoading}
      />
    )
  }

  return <>{desktopTable}</>
}
