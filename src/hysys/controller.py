from abc import ABC, abstractmethod


class HysysController(ABC):
    """应用层接口，不代表同名 HYSYS COM API 已存在或已验证。"""

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def create_case(self): ...

    @abstractmethod
    def configure_components(self, components): ...

    @abstractmethod
    def configure_property_package(self, name): ...

    @abstractmethod
    def create_feed_stream(self, inputs, info): ...

    @abstractmethod
    def create_conversion_reactor(self, info, inputs): ...

    @abstractmethod
    def create_equilibrium_reactor(self, info, inputs): ...

    @abstractmethod
    def create_gibbs_reactor(self, info, inputs): ...

    @abstractmethod
    def run(self): ...

    @abstractmethod
    def get_results(self): ...

    @abstractmethod
    def close(self): ...
