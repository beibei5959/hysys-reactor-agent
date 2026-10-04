from pydantic import ValidationError

from src.agent.llm import ModelChainError
from src.models.reaction import ReactionInfo
from src.runtime.telemetry import failure


def make_parse_node(llm):
    def parse_reaction(state):
        try:
            raw = state.get("reaction_info")
            inputs = state.get("simulation_inputs", {})
            if raw is None:
                if llm is None:
                    return {
                        "error": "未配置在线模型：自然语言解析暂不可用；可使用明确标注的离线结构化示例。",
                        "simulation_status": "failed",
                    }
                extracted = llm.extract(state["user_query"])
                if not isinstance(extracted, dict) or set(extracted) != {
                    "reaction_info",
                    "simulation_inputs",
                }:
                    raise ValueError("解析结果必须包含两个指定字段")
                raw = extracted["reaction_info"]
                inferred_inputs = extracted["simulation_inputs"]
                if not isinstance(inferred_inputs, dict):
                    raise ValueError("模拟参数须为对象")
                # 明确提供的结构化参数优先于模型提取值。
                inputs = {**inferred_inputs, **inputs}
            info = raw if isinstance(raw, ReactionInfo) else ReactionInfo.model_validate(raw)
            return {
                "reaction_info": info,
                "simulation_inputs": inputs,
                "error": None,
                "llm_trace": list(getattr(llm, "trace", [])),
            }
        except ModelChainError as exc:
            return {"error": str(exc), "simulation_status": "failed", "llm_trace": list(llm.trace)}
        except ValidationError as exc:
            fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
            return {"error": "反应信息格式/范围错误：" + fields, "simulation_status": "failed"}
        except Exception as exc:
            failure("parse_failed", exc)
            return {
                "error": "反应解析失败：请检查模型配置、服务响应及输入格式；没有执行模拟。",
                "simulation_status": "failed",
            }

    return parse_reaction
