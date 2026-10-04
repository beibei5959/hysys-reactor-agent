"""Restricted real COM integration for an existing toluene_python_test.hsc.

Does not create models or configure unverified reactor types. All requested
reference settings are checked before any write. No implicit active-case fallback.

Scale patch (documented, 2026-10-04): the feed guard is re-pinned from the
1000 kg/h development reference to the exam statement 10000 kg/h
(108.52955420760267 kmol/h = 10x the verified reference flow; HYSYS toluene
molar mass ~92.1408 kg/kmol). Only the extensive flow changes;
every intensive check (conversion, stoichiometry residuals, temperatures,
zero duty) and the reference_checks mass gate (feed_mass_10000_kg_h) remain
strict. Original Codex version preserved as backups/com_client.py.pre10000.bak.
"""
import time
from src.hysys.controller import HysysController
from src.hysys.exceptions import HysysError
from src.hysys import reference_checks as check


class ComHysysController(HysysController):
    supports_simulation = False

    def __init__(self):
        self.app = self.case = self.flowsheet = self._pythoncom = None
        self._result = None
        self._configured = False

    def connect(self):
        import pythoncom
        import win32com.client
        if self._pythoncom is not None:raise HysysError('Already connected')
        pythoncom.CoInitialize();self._pythoncom=pythoncom
        try:
            self.app=win32com.client.GetActiveObject('HYSYS.Application')
            self.case=self.app.ActiveDocument
            filename=str(self.case.UniqueID).rstrip('!').replace('\\','/').split('/')[-1]
            if filename.lower()!='toluene_python_test.hsc':
                raise HysysError('Open and activate toluene_python_test.hsc. Reference/original cases are not modified.')
            self.flowsheet=self.case.Flowsheet
            self.supports_simulation=True
        except Exception:
            self.close();raise

    def close(self):
        self.flowsheet=self.case=self.app=None
        if self._pythoncom is not None:self._pythoncom.CoUninitialize()
        self._pythoncom=None;self.supports_simulation=False

    def create_case(self):
        if self.case is None:raise HysysError('Not connected')
        # Interface compatibility only: reuse was explicitly selected above.

    def configure_components(self, components):
        names=[str(c.Name) for c in self.flowsheet.FluidPackage.Components]
        if names!=check.COMPONENTS or list(components)!=names:
            raise HysysError('Exact reference component names/order required; no writes performed.')

    def configure_property_package(self,name):
        if name!='Peng-Robinson' or str(self.flowsheet.FluidPackage.PropertyPackageName)!=name:
            raise HysysError('Peng-Robinson required; no writes performed.')

    def create_feed_stream(self,inputs,info):
        # Delay ALL writes until reactor settings and full request are checked.
        self._inputs,self._info=inputs,info

    def create_conversion_reactor(self,info,inputs):
        valid=(info.temperature==653.15 and info.pressure==2500 and info.conversion==.5
               and info.reactants==['Toluene'] and set(info.products)=={'Benzene','o-Xylene'}
               and inputs.feed_composition=={'Toluene':1.0}
               and inputs.conversion_basis=='Toluene'
               and check.close_enough(inputs.feed_flow_kmol_h,108.52955420760267)
               and inputs.reactions==[{'Toluene':-2.,'Benzene':1.,'o-Xylene':1.}])
        if not valid:raise HysysError('Only the fixed 50% ortho-toluene reference at the 10000 kg/h exam feed is supported. No writes performed.')
        op=self.flowsheet.Operations.Item('CRV-100')
        if str(op.TypeName)!='conversionreactorop' or bool(op.IsIgnored):
            raise HysysError('CRV-100 is not an active Conversion Reactor')
        reactions=list(op.ReactionSet.ActiveReactions)
        if len(reactions)!=1 or not bool(reactions[0].IsValid):raise HysysError('Expected one valid reaction')
        rxn=reactions[0]
        actual={str(r.Component.Name):float(r.StoichiometricCoefficientValue) for r in rxn.Reactants}
        expected=dict(zip(check.REFERENCE_SETTINGS['reactants'],check.REFERENCE_SETTINGS['stoichiometry']))
        if actual.keys()!=expected.keys() or not all(check.close_enough(actual[n],v) for n,v in expected.items()):
            raise HysysError('Existing reaction stoichiometry mismatch')
        if list(rxn.ConversionCoefficientsValue)!=[50.,0.,0.] or str(rxn.BaseComponent.Name)!='Toluene' or int(rxn.ReactionPhase)!=5:
            raise HysysError('Existing reaction must specify 50 percent on Toluene, Overall phase')
        if [str(s.Name) for s in op.AttachedFeeds]!=['FEED'] or {str(s.Name) for s in op.AttachedProducts}!={'PRODUCT','LIQUID_PROD'}:
            raise HysysError('Unexpected reactor stream connections')
        self._op=op;self._configured=True
        return op

    def create_equilibrium_reactor(self,*args):
        raise HysysError('Equilibrium implementation not verified; no feed writes performed')

    def create_gibbs_reactor(self,*args):
        raise HysysError('Gibbs implementation not verified; no feed writes performed')

    def run(self):
        if not self._configured:raise HysysError('Reference preflight not complete')
        solver=self.case.Solver
        if bool(solver.IsSolving) or bool(solver.IsForgetting):raise HysysError('Solver busy before update')
        previous=bool(solver.CanSolve)
        try:
            solver.CanSolve=False
            feed=self.flowsheet.MaterialStreams.Item('FEED')
            # Explicit units only; never fall back to raw Value units.
            feed.Temperature.SetValue(653.15,'K')
            feed.Pressure.SetValue(2500.,'kPa')
            import pythoncom
            import win32com.client
            feed.ComponentMolarFractionValue=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,[1.,0.,0.,0.,0.])
            feed.MolarFlow.SetValue(self._inputs.feed_flow_kmol_h,'kgmole/h')
            solver.CanSolve=True
            deadline=time.monotonic()+45;stable=0
            while time.monotonic()<deadline:
                self._pythoncom.PumpWaitingMessages();time.sleep(1)
                values={n:check.read_stream(self.flowsheet.MaterialStreams.Item(n),check.COMPONENTS) for n in ['FEED','PRODUCT','LIQUID_PROD']}
                v=check.calculate_checks(values['FEED'],[values['PRODUCT'],values['LIQUID_PROD']],check.COMPONENTS,bool(self._op.IsValid))
                conv=list(self._op.RxnPercentConversionValue)
                v['checks'].update(actual_conversion=len(conv)==1 and check.close_enough(conv[0],50,.01),
                    solver_idle=not bool(solver.IsSolving) and not bool(solver.IsForgetting),
                    zero_duty=check.close_enough(self._op.HeatFlow.GetValue('kJ/h'),0,.01),
                    feed_temperature=check.close_enough(values['FEED']['temperature_K'],653.15),
                    pure_feed=check.close_enough(values['FEED']['mole_fractions']['Toluene'],1),
                    pressure=all(check.close_enough(s['pressure_kPa'],2500,.1) for s in values.values()),
                    outlet_temperature=check.close_enough(values['PRODUCT']['temperature_K'],649.3400366698161,.02))
                v['all_checks_passed']=all(v['checks'].values())
                stable=stable+1 if v['all_checks_passed'] else 0
                if stable>=3:
                    self._result={'source':'hysys','converged':True,'workflow_verified':True,'reactor':'Conversion',
                        'execution_mode':'existing_reference_case_update','automatic_model_creation':False,
                        'case_unique_id':str(self.case.UniqueID),'case_saved':False,
                        'engineering_results':{'streams':values,'verification':v},
                        'limitations':['Fixed ortho-only existing test case at the 10000 kg/h exam feed; xylenes lumped to ortho (documented); not automatic model creation.']}
                    return
            raise HysysError('Real result validation failed; no success reported. Last checks: '+str(v['checks']))
        finally:
            solver.CanSolve=previous

    def get_results(self):
        if self._result is None:raise HysysError('No verified result')
        return self._result
