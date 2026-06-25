import { FormEvent, useState } from "react";

type Props = {
  disabled?: boolean;
  onSend: (question: string) => Promise<void>;
};

export default function MessageInput({ disabled = false, onSend }: Props) {
  const [value, setValue] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const question = value.trim();
    if (!question || disabled) return;
    setValue("");
    await onSend(question);
  }

  return (
    <form className="message-input" onSubmit={onSubmit}>
      <input
        disabled={disabled}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="输入问题，系统会检索 Excel 知识库并生成回答"
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        {disabled ? "生成中..." : "发送"}
      </button>
    </form>
  );
}
