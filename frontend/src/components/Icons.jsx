// Íconos de trazo (SVG en línea). Todos son decorativos: el texto o aria-label los acompaña.
const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }

export const PlusIcon = (p) => (
  <svg width="16" height="16" viewBox="0 0 24 24" {...base} {...p}><path d="M12 5v14M5 12h14" /></svg>
)
export const ChatIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><path d="M4 5h16v11H9l-5 4z" /></svg>
)
export const ClockIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>
)
export const FileIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4" /></svg>
)
export const LogoutIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10" /></svg>
)
export const SendIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><path d="M12 19V5M5 12l7-7 7 7" /></svg>
)
export const ExternalIcon = (p) => (
  <svg width="13" height="13" viewBox="0 0 24 24" {...base} {...p}><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" /></svg>
)
export const WarningIcon = (p) => (
  <svg width="20" height="20" viewBox="0 0 24 24" {...base} {...p}><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4M12 17.5v.01" /></svg>
)
export const SearchIcon = (p) => (
  <svg width="16" height="16" viewBox="0 0 24 24" {...base} {...p}><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4 4" /></svg>
)
export const UploadIcon = (p) => (
  <svg width="32" height="32" viewBox="0 0 24 24" {...base} {...p}><path d="M12 15V4M7 9l5-5 5 5M4 15v5h16v-5" /></svg>
)
export const TrashIcon = (p) => (
  <svg width="17" height="17" viewBox="0 0 24 24" {...base} {...p}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg>
)
export const CheckIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
)
export const VideoIcon = (p) => (
  <svg width="18" height="18" viewBox="0 0 24 24" {...base} {...p}><rect x="3" y="5" width="13" height="14" rx="2" /><path d="M16 10l5-3v10l-5-3z" /></svg>
)
export const LockIcon = (p) => (
  <svg width="14" height="14" viewBox="0 0 24 24" {...base} {...p}><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
)
