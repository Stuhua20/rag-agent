export default function TopBar({ title = "知循 · KnowLoop" }: { title?: string }) {
  return (
    <header className="topbar">
      <strong className="topbar-title" title={title}>{title}</strong>
    </header>
  );
}

