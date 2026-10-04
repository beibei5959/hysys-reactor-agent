from src.hysys.exceptions import HysysError, RetryableHysysError
from src.runtime.telemetry import failure


def make_run_node(runner, max_retries):
    def run_hysys(state):
        try:
            results = runner(
                state["selected_reactor"], state["reaction_info"], state["simulation_inputs"]
            )
            if results.get("source") not in {"mock", "hysys"}:
                raise HysysError("模拟结果缺少可信的数据来源标志")
            ok = (
                results.get("workflow_verified") is True
                if results["source"] == "mock"
                else results.get("converged") is True
            )
            if not ok:
                raise HysysError("模拟未收敛或流程未完成；不输出工程结果")
            return {
                "simulation_results": results,
                "simulation_status": "success",
                "error": None,
                "error_code": None,
                "cleanup_status": results.get("cleanup_status", "success"),
            }
        except RetryableHysysError as exc:
            # 节点只负责判定重试条件与递增计数；退避 sleep 由外层 observer 执行，
            # 避免在 web 线程池里长期阻塞 worker slot。
            count = state.get("retry_count", 0)
            if count < max_retries:
                return {
                    "retry_count": count + 1,
                    "simulation_status": "retrying",
                    "error": str(exc),
                    "simulation_results": {},
                }
            return {
                "simulation_status": "failed",
                "error_code": "RETRY_EXHAUSTED",
                "error": "有限重试次数已用尽：" + str(exc),
                "simulation_results": {},
            }
        except HysysError as exc:
            failure("simulation_failed", exc)
            return {
                "simulation_status": "failed",
                "error_code": "SIMULATION_FAILED",
                "error": str(exc),
                "simulation_results": {},
            }
        except Exception as exc:
            failure("simulation_outcome_unknown", exc)
            return {
                "simulation_status": "outcome_unknown",
                "error_code": "OUTCOME_UNKNOWN",
                "error": "模拟调用异常，执行结果待核对；禁止自动重试。",
                "simulation_results": {},
            }

    return run_hysys
