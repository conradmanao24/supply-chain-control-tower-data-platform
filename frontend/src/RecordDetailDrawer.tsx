import type { ReactNode } from 'react'
import { X } from 'lucide-react'

type Props = {
  kicker: string
  title: string
  status?: ReactNode
  onClose: () => void
  children: ReactNode
  loading?: boolean
  className?: string
}

export default function RecordDetailDrawer({
  kicker,
  title,
  status,
  onClose,
  children,
  loading = false,
  className = '',
}: Props) {
  return (
    <>
      <button
        className="record-drawer-backdrop"
        aria-label="Close record detail"
        onClick={onClose}
      />
      <aside className={'record-drawer ' + className} aria-label={kicker}>
        <header className="record-drawer-header">
          <div>
            <span className="panel-kicker">{kicker}</span>
            <h3>{title}</h3>
          </div>
          <div className="record-drawer-header-actions">
            {status}
            <button className="icon-button" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
          </div>
        </header>
        <div className="record-drawer-body">
          {loading ? <div className="record-drawer-loading">Loading record detail...</div> : children}
        </div>
      </aside>
    </>
  )
}
