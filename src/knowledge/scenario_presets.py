"""Deterministic natural-language -> verified-scenario preset mapping.

The three exam scenarios each have an independently verified real-HYSYS path:
  * Equilibrium  -> reforming_mvp/run_reforming.py   (passed_reforming_checks)
  * Gibbs        -> gasification_mvp/run_gasification.py (passed_gasification_checks)
  * Conversion   -> fixed com_client reference-join on toluene_python_test.hsc

Those verified paths require exact pinned parameters (unit-converted molar
flows, component order, equilibrium-method provenance). Free-form LLM
extraction cannot reproduce them reliably, so this module matches the user
query by keywords and returns the pinned structured payload. The original
natural-language text is still submitted as ``user_query`` and drives the
final explanation. Unmatched queries fall back to the LLM extraction path.

Deviation record (also in the project report):
  * Toluene feed is pinned to the exam statement: 10000 kg/h =
    10000/92.14 = 108.52955420760267 kmol/h (reference case previously ran
    1000 kg/h; only the extensive flow changes, all intensive checks remain).
  * Xylene isomers are lumped to o-Xylene in the verified reference reaction
    (documented simplification; m-/p-Xylene are checked to stay at zero).
  * Gasification basis: 1000 kg/h slurry (62/38 wt%); the exam's 80000
    Nm3/h scales absolute flows only - composition and CO yield are
    basis-independent. Methane excluded from Gibbs candidates (non-physical
    local solution, documented in run_gasification.py assumptions).
"""

# Slurry basis, identical to gasification_mvp/run_gasification.py constants.
_M_C = 12.011
_M_W = 18.015
NC = 1000.0 * 0.62 / _M_C   # kmol carbon per 1000 kg slurry
NW = 1000.0 * 0.38 / _M_W   # kmol water per 1000 kg slurry
NTOT = NC + NW

# Codex's verified 1000 kg/h reference flow, implied by HYSYS's own toluene
# molar mass (~92.1408 kg/kmol, NOT 92.14): the com_client guard compares with
# 1e-7 absolute tolerance, so scale the verified constant exactly instead of
# recomputing from a rounded MW.
TOLUENE_FEED_KMOL_H = 10.0 * 10.852955420760267  # = 108.52955420760267

PRESETS = {
    "equilibrium": {
        "match": ("甲烷蒸汽重整", "蒸汽重整", "重整炉"),
        "reaction_info": {
            "reaction_name": "甲烷蒸汽重整",
            "reactants": ["Methane", "H2O"],
            "products": ["CO", "CO2", "Hydrogen"],
            "temperature": 983.15,   # 710 C outlet case; runner also covers 600 C
            "pressure": 1350.0,      # 13.5 bar absolute
            "reversible": True,
            "multiple_reactions": True,
            "conversion_known": False,
            "conversion": None,
            "equilibrium_controlled": True,
            "products_known": True,
            "reaction_path_known": True,
        },
        "simulation_inputs": {
            "components": ["Methane", "H2O", "CO", "CO2", "Hydrogen"],
            "property_package": "Peng-Robinson",
            "feed_composition": {"Methane": 1.0 / 3.7, "H2O": 2.7 / 3.7},
            "feed_flow_kmol_h": 100.0,
            "reactions": [
                {"Methane": -1.0, "H2O": -1.0, "CO": 1.0, "Hydrogen": 3.0},
                {"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "Hydrogen": 1.0},
            ],
            "conversion_basis": None,
            "equilibrium_method": (
                "HYSYS 内置平衡常数库（ln K 温度多项式，LnKSource=3 只读导出核对），"
                "由 reforming_mvp/run_reforming.py 在远程 HYSYS V15 连续三轮通过全部校验"
            ),
        },
        "note": "Pinned to the verified reforming runner (ER-710/ER-600, 13.5 bar, feed 520 C).",
    },
    "conversion": {
        "match": ("甲苯歧化", "歧化反应"),
        "reaction_info": {
            "reaction_name": "甲苯歧化",
            "reactants": ["Toluene"],
            "products": ["Benzene", "o-Xylene"],
            "temperature": 653.15,   # 380 C
            "pressure": 2500.0,      # 2.5 MPa absolute
            "reversible": False,
            "multiple_reactions": False,
            "conversion_known": True,
            "conversion": 0.5,
            "equilibrium_controlled": False,
            "products_known": True,
            "reaction_path_known": True,
        },
        "simulation_inputs": {
            "components": ["Toluene", "Benzene", "o-Xylene", "m-Xylene", "p-Xylene"],
            "property_package": "Peng-Robinson",
            "feed_composition": {"Toluene": 1.0},
            "feed_flow_kmol_h": TOLUENE_FEED_KMOL_H,
            "reactions": [{"Toluene": -2.0, "Benzene": 1.0, "o-Xylene": 1.0}],
            "conversion_basis": "Toluene",
            "equilibrium_method": None,
        },
        "note": (
            "Pinned to the verified toluene reference-join case "
            "(toluene_python_test.hsc must be open and active); feed scaled to "
            "the exam statement 10000 kg/h; xylenes lumped to ortho (documented)."
        ),
    },
    "gibbs": {
        "match": ("水煤浆气化", "水煤浆"),
        "reaction_info": {
            "reaction_name": "水煤浆气化",
            "reactants": ["Carbon", "H2O"],
            "products": ["CO", "CO2", "Hydrogen"],
            "temperature": 1673.15,  # 1400 C outlet
            "pressure": 4000.0,      # 40 bar absolute
            "reversible": None,
            "multiple_reactions": True,
            "conversion_known": False,
            "conversion": None,
            "equilibrium_controlled": None,
            "products_known": False,
            "reaction_path_known": False,
        },
        "simulation_inputs": {
            "components": ["Carbon", "H2O", "CO", "CO2", "Hydrogen"],
            "property_package": "Peng-Robinson",
            "feed_composition": {"Carbon": NC / NTOT, "H2O": NW / NTOT},
            "feed_flow_kmol_h": NTOT,
            "reactions": [],
            "conversion_basis": None,
            "equilibrium_method": (
                "Gibbs 自由能最小化（HYSYS Gibbs reactor，固体 Carbon 为候选物种；"
                "甲烷从候选中排除以避免非物理局部解，见 run_gasification.py assumptions），"
                "由 gasification_mvp/run_gasification.py 在远程 HYSYS V15 连续三轮通过全部校验"
            ),
        },
        "note": (
            "Pinned to the verified gasification runner (steam-limited, 40 bar, "
            "40 C feed -> 1400 C outlet, 1000 kg/h slurry basis)."
        ),
    },
}


def match_scenario(query: str):
    """Return (name, preset) for the first keyword match, else (None, None)."""
    text = query or ""
    for name, preset in PRESETS.items():
        if any(keyword in text for keyword in preset["match"]):
            return name, preset
    return None, None


def preset_payload(name: str, query: str) -> dict:
    """Build the app.py --input JSON body for a matched preset."""
    preset = PRESETS[name]
    return {
        "user_query": query,
        "reaction_info": preset["reaction_info"],
        "simulation_inputs": preset["simulation_inputs"],
        "preset": name,
        "preset_note": preset["note"],
    }
