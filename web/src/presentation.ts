import type { Task } from "./types";

const fields: Record<string, string> = {
  property_package: "物性包",
  feed_composition: "进料摩尔分率",
  feed_flow_kmol_h: "进料总摩尔流量（kmol/h）",
  components: "候选组分",
  reactions: "反应计量方程",
  conversion_basis: "转化基准组分",
  equilibrium_method: "平衡数据来源或方法",
  temperature: "温度",
  pressure: "绝对压力",
  reactants: "反应物",
  products: "产物",
  conversion: "转化率",
  reaction_info: "反应信息",
  simulation_inputs: "模拟参数",
  conversion_known: "是否给定转化率",
  reversible: "是否可逆",
  multiple_reactions: "是否为多反应体系",
  equilibrium_controlled: "是否受平衡控制",
  products_known: "产物是否明确",
  reaction_path_known: "反应路径是否明确",
};

export function readable(text: string) {
  return text.replace(/\b[a-z][a-z_]*\b/g, (value) => fields[value] ?? value);
}

export function currentStage(
  task: Task,
  stageLabels: string[],
  stages: string[],
) {
  const status: Record<string, string> = {
    needs_input: "等待补充参数",
    awaiting_confirmation: "等待确认参数",
    completed:
      task.state.simulation_results?.source === "mock"
        ? "Mock 流程已完成"
        : "任务已完成",
    failed: "执行失败",
    interrupted: "执行中断，等待恢复",
    outcome_unknown: "执行结果待人工核对",
    pending: "已排队，等待执行",
  };
  return (
    status[task.status] ??
    stageLabels[stages.indexOf(task.stage ?? "")] ??
    "等待状态更新"
  );
}
