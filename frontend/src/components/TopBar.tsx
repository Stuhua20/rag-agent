export default function TopBar({ title = "知识库检索工具" }: { title?: string }) {
  return (
    <header className="topbar">
      <strong className="topbar-title" title={title}>{title}</strong>
    </header>
  );
}

