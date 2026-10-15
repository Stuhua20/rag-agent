type Props = { name: "file" | "copy" | "panel" | "close" };

export default function ChatIcon({ name }: Props) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {name === "file" && <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></>}
      {name === "copy" && <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>}
      {name === "panel" && <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></>}
      {name === "close" && <path d="m6 6 12 12M6 18 18 6" />}
    </svg>
  );
}
