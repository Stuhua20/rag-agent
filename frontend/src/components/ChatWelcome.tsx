import ChatIcon from "./ChatIcon";

export default function ChatWelcome() {
  return (
    <section className="chat-welcome" aria-labelledby="chat-welcome-title">
      <div className="chat-welcome-icon"><ChatIcon name="file" /></div>
      <p className="chat-welcome-eyebrow">知循 · KnowLoop</p>
      <h1 id="chat-welcome-title">从知识库中，找到你需要的答案</h1>
      <p className="chat-welcome-description">用自然语言检索已入库文档，结合来源证据获取回答。</p>
      <p className="chat-welcome-guide">直接在下方输入问题，或先选择文档缩小检索范围。</p>
    </section>
  );
}
