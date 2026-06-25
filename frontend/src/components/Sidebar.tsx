import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "聊天" },
  { to: "/upload", label: "上传" },
  { to: "/documents", label: "文件库" },
  { to: "/settings", label: "设置" },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">Excel RAG</div>
      <button className="new-chat">+ 新建对话</button>
      <nav className="nav-list">
        {links.map((link) => (
          <NavLink key={link.to} to={link.to} className={({ isActive }) => (isActive ? "active" : "")}>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-note">阶段三：Excel/CSV 入库已启用</div>
    </aside>
  );
}

