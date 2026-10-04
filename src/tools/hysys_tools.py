from src.hysys.exceptions import HysysError
from src.models.simulation import SimulationInputs
from src.runtime.telemetry import failure

# Reactor type -> independently verified scenario runner (real HYSYS mode only).
# Conversion is absent on purpose: its verified path is the reference-join
# sequence inside the fixed com_client (legacy controller calls below);
# routing it through app.py here would recurse.
VERIFIED_SCENARIO = {"Equilibrium": "equilibrium", "Gibbs": "gibbs"}


def make_hysys_runner(controller_factory):
    def run(reactor, info, raw_inputs):
        inputs = SimulationInputs.model_validate(raw_inputs)
        if getattr(controller_factory, "__name__", "") == "ComHysysController" and reactor in VERIFIED_SCENARIO:
            # Real mode delegates to the scenario runners that passed strict
            # remote HYSYS verification; mock mode keeps the legacy path.
            from src.hysys.verified_runners import run_verified_scenario
            results = run_verified_scenario(VERIFIED_SCENARIO[reactor])
            if not results.get("converged"):
                raise HysysError(str(results.get("error") or "verified scenario runner did not converge"))
            results["cleanup_status"] = "success"
            return results
        controller = controller_factory()
        results = None
        cleanup_failed = False
        try:
            controller.connect()
            # supports_simulation 只在 connect() 之后可信：COM 适配器连上
            # 活动案例后才把它置 True，连接前检查会误判为仅诊断适配器。
            if not getattr(controller, "supports_simulation", True):
                raise HysysError("当前 HYSYS 适配器仅支持连接诊断，不支持执行计算")
            controller.create_case()
            controller.configure_components(inputs.components)
            controller.configure_property_package(inputs.property_package)
            controller.create_feed_stream(inputs, info)
            creators = {
                "Conversion": controller.create_conversion_reactor,
                "Equilibrium": controller.create_equilibrium_reactor,
                "Gibbs": controller.create_gibbs_reactor,
            }
            if reactor not in creators:
                raise HysysError("未知反应器类型")
            creators[reactor](info, inputs)
            controller.run()
            results = controller.get_results()
        finally:
            try:
                controller.close()
            except Exception as exc:
                failure("controller_cleanup_failed", exc)
                cleanup_failed = True
        if results is not None:
            # 单次赋值：正常路径 success，close 异常时覆盖为 failed；不在返回后再次 mutate。
            results["cleanup_status"] = "failed" if cleanup_failed else "success"
        return results

    return run
