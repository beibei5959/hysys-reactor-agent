from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReactionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    reaction_name: str | None = None
    reactants: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    temperature: float | None = Field(default=None, gt=0, description="K")
    pressure: float | None = Field(default=None, gt=0, description="kPa absolute")
    reversible: bool | None = None
    multiple_reactions: bool | None = None
    conversion_known: bool | None = None
    conversion: float | None = Field(default=None, ge=0, le=1)
    equilibrium_controlled: bool | None = None
    products_known: bool | None = None
    reaction_path_known: bool | None = None

    @model_validator(mode="after")
    def consistent_conversion(self):
        if self.conversion is not None:
            if self.conversion_known is False:
                raise ValueError("提供转化率时 conversion_known 不能为 False")
            self.conversion_known = True
        return self
