import type { AgentStep, ChatMessage } from "../types/chat";

const STATUS_LABELS: Record<string, string> = {
  answered: "回答完成", clarification_required: "等待补充信息", insufficient_evidence: "依据不足",
  verification_failed: "回答未通过校验", failed: "处理失败", cancelled: "处理已中断",
  review_unavailable: "证据审查未完成", budget_exceeded: "已达到执行预算",
  partially_answered: "部分分析完成", calculation_failed: "计算未完成", unsupported: "当前能力不支持",
};

function storedSteps(message: ChatMessage): AgentStep[] {
  if (message.agent_steps) return message.agent_steps;
  const agent = message.quality?.agent;
  if (!agent || typeof agent !== "object" || !("steps" in agent) || !Array.isArray(agent.steps)) return [];
  return agent.steps.filter((item): item is AgentStep => item && typeof item.step_id === "string"
    && typeof item.label === "string" && (item.event === "step_started" || item.event === "step_done"));
}

export default function AgentProgress({ message }: { message: ChatMessage }) {
  const steps = new Map<string, AgentStep>();
  for (const step of storedSteps(message)) steps.set(step.step_id, step);
  if (!message.run_id && steps.size === 0) return null;
  const agent = message.quality?.agent;
  const storedStatus = agent && typeof agent === "object" && "status" in agent && typeof agent.status === "string" ? agent.status : undefined;
  const status = message.status ?? storedStatus ?? "running";
  const active = status === "running";
  const interrupted = status === "failed" || status === "cancelled";
  const values = [...steps.values()];
  const last = values[values.length - 1];
  const label = active ? last?.label ?? "正在准备检索" : STATUS_LABELS[status] ?? "处理结束";
  const review = message.quality?.evidence_review;
  const reviewLabel = review?.mode === "mock" ? "模拟模式，未进行真实证据审查"
    : review?.mode === "disabled" || review?.mode === "legacy" ? "本轮未启用语义审查"
    : review?.passed === true ? `证据审查通过${review.revision_round ? "，已修订一次" : ""}`
    : review?.passed === false ? "回答未通过证据审查"
    : review?.status === "skipped" ? "本轮未进入语义审查" : "证据审查未完成";
  const issues = [...new Set((review?.history ?? []).flatMap((entry) => [
    ...(entry.units ?? []).flatMap((unit) => unit.issues),
    ...(entry.tasks ?? []).filter((task) => task.status === "omitted" || task.status === "uncertain").map((task) => task.reason),
  ]))];
  return (
    <details className={`agent-progress${active ? " is-running" : ""}`}>
      <summary><span className="agent-progress-dot" aria-hidden="true" /><span role="status">{label}</span><span className="agent-progress-hint">执行过程</span></summary>
      <ol>{[...steps.values()].map((step) => (
        <li key={step.step_id} className={active && step.event === "step_started" ? "is-active" : ""}>
          <span aria-hidden="true">{step.event === "step_started" && interrupted ? "!" : active && step.event === "step_started" ? "·" : "✓"}</span>{step.label}
          {step.step_id.startsWith("replan:") && <span className="agent-progress-round">补充检索</span>}
        </li>
      ))}</ol>
      {!active && review && <div className="agent-review-summary">
        <p>{reviewLabel}</p>
        {issues.length > 0 && <ul>{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
      </div>}
    </details>
  );
}
