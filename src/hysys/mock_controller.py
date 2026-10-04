from src.hysys.controller import HysysController
from src.hysys.exceptions import HysysError


class MockHysysController(HysysController):
    """只验证调用顺序及参数传递；不模拟真实物理结果。"""

    def __init__(self):
        self.calls = []
        self.reactor = None
        self.closed = False

    def connect(self):
        self.calls.append("connect")

    def create_case(self):
        self.calls.append("create_case")

    def configure_components(self, components):
        self.components = list(components)
        self.calls.append("configure_components")

    def configure_property_package(self, name):
        self.property_package = name
        self.calls.append("configure_property_package")

    def create_feed_stream(self, inputs, info):
        self.feed = inputs.model_dump()
        self.conditions = {
            "temperature_K": info.temperature,
            "pressure_kPa_absolute": info.pressure,
        }
        self.calls.append("create_feed_stream")

    def create_conversion_reactor(self, info, inputs):
        self.reactor = "Conversion"
        self.calls.append("create_conversion_reactor")

    def create_equilibrium_reactor(self, info, inputs):
        self.reactor = "Equilibrium"
        self.calls.append("create_equilibrium_reactor")

    def create_gibbs_reactor(self, info, inputs):
        self.reactor = "Gibbs"
        self.calls.append("create_gibbs_reactor")

    def run(self):
        if (
            self.calls[:5]
            != [
                "connect",
                "create_case",
                "configure_components",
                "configure_property_package",
                "create_feed_stream",
            ]
            or self.reactor is None
        ):
            raise HysysError("Mock 调用顺序错误")
        self.calls.append("run")

    def get_results(self):
        if not self.calls or self.calls[-1] != "run":
            raise HysysError("Mock 尚未执行")
        self.calls.append("get_results")
        return {
            "source": "mock",
            "workflow_verified": True,
            "converged": None,
            "reactor": self.reactor,
            "engineering_results": None,
        }

    def close(self):
        self.closed = True
        self.calls.append("close")
