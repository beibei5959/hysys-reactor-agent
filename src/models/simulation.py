from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    components: list[str] = Field(min_length=1)
    property_package: str = Field(min_length=1)
    feed_composition: dict[str, float]
    feed_flow_kmol_h: float = Field(gt=0)
    reactions: list[dict[str, float]] = Field(default_factory=list)
    conversion_basis: str | None = None
    equilibrium_method: str | None = None

    @model_validator(mode="after")
    def check_consistency(self):
        if any(not c.strip() for c in self.components) or len(set(self.components)) != len(
            self.components
        ):
            raise ValueError("候选组分必须非空且不重复")
        if not self.property_package.strip():
            raise ValueError("物性包不能为空")
        if not self.feed_composition or not set(self.feed_composition) <= set(self.components):
            raise ValueError("进料组分必须属于候选组分")
        if any(v < 0 or v > 1 for v in self.feed_composition.values()):
            raise ValueError("摩尔分率必须为 0～1")
        if abs(sum(self.feed_composition.values()) - 1) > 1e-6:
            raise ValueError("进料摩尔分率之和必须为 1")
        for reaction in self.reactions:
            if not set(reaction) <= set(self.components):
                raise ValueError("反应计量中的组分必须属于候选组分")
            if not any(v < 0 for v in reaction.values()) or not any(
                v > 0 for v in reaction.values()
            ):
                raise ValueError("计量反应须同时包含负的反应物系数和正的产物系数")
        return self
