"""Two genuine HYSYS equilibrium-reactor cases in one flowsheet. No LLM yet."""
import json, math, subprocess, sys, time, traceback
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NAMES=['Methane','H2O','CO','CO2','Hydrogen']
COEFF={
 'WGS':[-12.10761428743534,5318.690079942231,1.0120500906868166,.00011436733968163935],
 'SMR':[-20.55224251858141,-22920.57919535056,7.194621662044369,-.0029494193719204476]}
STOICH={'WGS':{'CO':-1.,'H2O':-1.,'CO2':1.,'Hydrogen':1.},
        'SMR':{'Methane':-1.,'H2O':-1.,'CO':1.,'Hydrogen':3.}}

def kvalue(name,t):
 a,b,c,d=COEFF[name]
 return math.exp(a+b/t+c*math.log(t)+d*t)

def finite(v):
 v=float(v)
 if not math.isfinite(v) or v==-32767.:raise ValueError('Undefined HYSYS value')
 return v

def read_stream(s,names):
 flow=finite(s.MolarFlow.GetValue('kgmole/h'))
 if flow < -1e-7:raise ValueError('Negative flow')
 z=[finite(v) for v in s.ComponentMolarFractionValue] if flow>1e-8 else [0.]*len(names)
 if len(z)!=len(names):raise ValueError('Composition size mismatch')
 if flow>1e-8 and (abs(sum(z)-1)>1e-6 or min(z)<-1e-8):raise ValueError('Invalid composition')
 return dict(temperature_K=finite(s.Temperature.GetValue('K')),pressure_kPa=finite(s.Pressure.GetValue('kPa')),
   molar_flow_kmol_h=flow,mass_flow_kg_h=finite(s.MassFlow.GetValue('kg/h')),
   mole_fractions=dict(zip(names,z)),component_flow_kmol_h={n:flow*x for n,x in zip(names,z)})

def checks(feed,vap,liq,tc,valid):
 f=feed['component_flow_kmol_h'];out={n:vap['component_flow_kmol_h'][n]+liq['component_flow_kmol_h'][n] for n in NAMES}
 x=100.-out['Methane'];y=out['CO2']
 expected={'Methane':100-x,'H2O':270-x-y,'CO':x-y,'CO2':y,'Hydrogen':3*x+y}
 mass=abs(feed['mass_flow_kg_h']-vap['mass_flow_kg_h']-liq['mass_flow_kg_h'])
 p={n:max(0.,v)*vap['pressure_kPa']/101.325 for n,v in vap['mole_fractions'].items()}
 q={}
 try:
  q={'WGS':p['CO2']*p['Hydrogen']/(p['CO']*p['H2O']),
     'SMR':p['CO']*p['Hydrogen']**3/(p['Methane']*p['H2O'])}
 except ZeroDivisionError:pass
 eq={n:kvalue(n,tc+273.15) for n in COEFF}
 tests={
  'reactor_valid':bool(valid),
  'feed_temperature':abs(feed['temperature_K']-793.15)<.02,
  'feed_pressure':abs(feed['pressure_kPa']-1350)<.1,
  'feed_components':all(abs(f[n]-({'Methane':100.,'H2O':270.}.get(n,0.)))<.001 for n in NAMES),
  'outlet_temperature':abs(vap['temperature_K']-(tc+273.15))<.02,
  'outlet_pressure':abs(vap['pressure_kPa']-1350)<.1,
  'mass_balance':mass<max(.05,abs(feed['mass_flow_kg_h'])*1e-4),
  'reaction_component_balance':all(abs(out[n]-expected[n])<.01 for n in NAMES),
  'positive_reaction':0<x<100 and 0<y<x,
  'vapour_only_at_target':abs(liq['molar_flow_kmol_h'])<1e-5,
  'equilibrium_quotients':len(q)==2 and all(q[n]>0 and abs(math.log(q[n]/eq[n]))<.02 for n in eq)}
 return dict(checks=tests,all_checks_passed=all(tests.values()),methane_conversion_percent=x,
   mass_residual_kg_h=mass,equilibrium_K_atm_basis=eq,reaction_quotients_atm_basis=q,
   outlet_component_flow_kmol_h=out)

def build(app,r,array):
 cases=app.SimulationCases;old={str(c.UniqueID) for c in cases}
 r['stage']='create_independent_case'
 case=cases.Add();identity=str(case.UniqueID)
 if identity in old:raise RuntimeError('Independent case not created')
 r['case_unique_id']=identity;case.Visible=True;case.Activate()
 b=case.BasisManager;fs=case.Flowsheet
 r['stage']='create_basis';b.StartBasisChange()
 cl=b.ComponentLists.Add('Reforming-Components')
 for n in NAMES:cl.Components.Add(n)
 if [str(c.Name) for c in cl.Components]!=NAMES:raise RuntimeError('Component name/order mismatch')
 fp=b.FluidPackages.Add('Reforming-PR');fp.ComponentList=cl;fp.PropertyPackageName='PengRob';fs.FluidPackage=fp
 if str(fp.PropertyPackageName)!='Peng-Robinson':raise RuntimeError('Property method mismatch')
 rpm=b.ReactionPackageManager;rs=rpm.ReactionSets.Add('Reforming-Set')
 r['reaction_settings']={}
 for name,sto in STOICH.items():
  r['stage']='configure_reaction:'+name
  rx=rpm.Reactions.Add(name,'equilibriumrxn')
  for n,nu in sto.items():rx.Reactants.Add(n).StoichiometricCoefficientValue=nu
  rx.Basis=2;rx.BasisUnits2='atm';rx.ReactionPhase=0
  rx.AutoDetect=False
  rx.EquilibriumConstantParameterArrayValue=array(COEFF[name]+[0.]*4)
  rx.LnKSource=1
  got=list(rx.EquilibriumConstantParameterArrayValue)
  r['reaction_settings'][name]=dict(type=str(rx.TypeName),basis=int(rx.Basis),units=str(rx.BasisUnits2),phase=int(rx.ReactionPhase),lnk_source=int(rx.LnKSource),coefficients=got)
  if len(got)!=8 or any(abs(a-b)>1e-9 for a,b in zip(got,COEFF[name]+[0.]*4)):raise RuntimeError('Coefficient readback mismatch')
  if int(rx.Basis)!=2 or str(rx.BasisUnits2)!='atm' or int(rx.ReactionPhase)!=0:raise RuntimeError('Reaction basis readback mismatch')
  rs.ActiveReactions.Add(name)
 rs.AssociateFluidPackage(fp)
 if not b.CanEndBasisChange:raise RuntimeError('Reaction basis incomplete')
 b.EndBasisChange()
 solver=case.Solver;previous=bool(solver.CanSolve)
 try:
  solver.CanSolve=False
  for tc in [600,710]:
   tag=str(tc);r['stage']='create_reactor:'+tag
   feed=fs.MaterialStreams.Add('FEED-'+tag)
   feed.Temperature.SetValue(793.15,'K');feed.Pressure.SetValue(1350.,'kPa')
   feed.ComponentMolarFractionValue=array([100/370,270/370,0.,0.,0.]);feed.MolarFlow.SetValue(370.,'kgmole/h')
   vap=fs.MaterialStreams.Add('VAP-'+tag);liq=fs.MaterialStreams.Add('LIQ-'+tag)
   energy=fs.EnergyStreams.Add('Q-'+tag)
   op=fs.Operations.Add('ER-'+tag,'equilibriumreactorop')
   op.Feeds.Add(feed);op.VapourProduct=vap;op.LiquidProduct=liq;op.EnergyStream=energy;op.ReactionSet=rs
   op.PressureDrop.SetValue(0.,'kPa')
   r['stage']='specify_outlet_temperature:'+tag
   vap.Temperature.SetValue(tc+273.15,'K')
 finally:solver.CanSolve=previous
 if not previous:case.Solver.CanSolve=True
 r['status']='awaiting_verification';r['stage']='build_process_finished'


def verify(app,r):
 identity=r['case_unique_id'];matches=[c for c in app.SimulationCases if str(c.UniqueID)==identity]
 if len(matches)!=1:raise RuntimeError('Exact built case not found')
 case=matches[0];fs=case.Flowsheet
 names=[str(c.Name) for c in fs.FluidPackage.Components]
 if names!=NAMES:raise RuntimeError('Wrong component order')
 rs=case.BasisManager.ReactionPackageManager.ReactionSets.Item('Reforming-Set')
 stable=0;r['stage']='verify_two_temperatures';deadline=time.monotonic()+60
 while time.monotonic()<deadline:
  time.sleep(1)
  try:
   sol=case.Solver;idle=bool(sol.CanSolve) and not bool(sol.IsSolving) and not bool(sol.IsForgetting)
   r['solver_idle']=idle;r['results']={}
   for tc in [600,710]:
    tag=str(tc);op=fs.Operations.Item('ER-'+tag)
    feed=read_stream(fs.MaterialStreams.Item('FEED-'+tag),names)
    vap=read_stream(fs.MaterialStreams.Item('VAP-'+tag),names);liq=read_stream(fs.MaterialStreams.Item('LIQ-'+tag),names)
    result=checks(feed,vap,liq,tc,op.IsValid)
    result['checks']['reaction_set_attached']=str(op.ReactionSet.UniqueID)==str(rs.UniqueID)
    result['checks']['reactor_not_ignored']=not bool(op.IsIgnored)
    result['checks']['solver_idle']=idle
    result['all_checks_passed']=all(result['checks'].values())
    result.update(feed=feed,vapour_product=vap,liquid_product=liq,heat_duty_kJ_h=finite(op.HeatFlow.GetValue('kJ/h')),reactor_type=str(op.TypeName))
    r['results'][tag]=result
   good=all(v['all_checks_passed'] for v in r['results'].values())
   stable=stable+1 if good else 0
   if stable>=3:break
  except Exception:
   stable=0;r['last_poll_error']=traceback.format_exc()
 else:raise RuntimeError('Two-temperature verification did not pass. Inspect results; no success claimed.')
 r['stage']='save_verified_case'
 path=Path(r['planned_case_file'])
 if path.exists():raise FileExistsError(path)
 case.SaveAs2(str(path),False)
 if not path.is_file() or path.stat().st_size==0:raise RuntimeError('Saved file missing')
 r.update(status='passed_reforming_checks',stage='finished',saved_case=str(path),consecutive_passing_samples=stable)


def worker(phase,path):
 import pythoncom,win32com.client
 r=json.loads(path.read_text(encoding='utf-8'));app=None
 pythoncom.CoInitialize()
 try:
  app=win32com.client.GetActiveObject('HYSYS.Application')
  if phase=='build':build(app,r,lambda v:win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,v))
  else:
   if r['status']!='awaiting_verification':raise RuntimeError('Build not complete')
   verify(app,r)
 except Exception:r['status']='failed';r['error']=traceback.format_exc()
 finally:app=None;pythoncom.CoUninitialize()
 path.write_text(json.dumps(r,ensure_ascii=True,indent=2,allow_nan=False),encoding='utf-8')
 return 0 if r['status'] in ['awaiting_verification','passed_reforming_checks'] else 1


def main():
 if len(sys.argv)==3:return worker(sys.argv[1],Path(sys.argv[2]))
 folder=ROOT/'diagnostics';folder.mkdir(exist_ok=True)
 generated=ROOT/'generated_cases';generated.mkdir(exist_ok=True)
 stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f');path=folder/('reforming_'+stamp+'.json')
 r=dict(source='hysys',status='not_started',stage='start',scope='MVP automatic equilibrium-reforming simulation; no natural-language integration yet',
  assumptions=['Feed methane 100 kmol/h plus steam 270 kmol/h','Inlet 520 C; outlet 600 C and 710 C; pressure 13.5 bar interpreted as absolute; zero pressure drop',
   'Gas-phase partial-pressure equilibrium in atm, using full-precision HYSYS library ln(K) fits; PR physical properties; heat duty calculated',
   'Only steam reforming and water-gas shift; no solid carbon reaction'],
  planned_case_file=str(generated/('reforming_'+stamp+'.hsc')))
 path.write_text(json.dumps(r,indent=2),encoding='utf-8')
 try:
  for phase in ['build','verify']:
   print('HYSYS phase:',phase,flush=True)
   p=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),phase,str(path)],timeout=120)
   if p.returncode!=0:break
 except Exception:
  r=json.loads(path.read_text(encoding='utf-8'));r.update(status='outcome_unknown',controller_error=traceback.format_exc())
  path.write_text(json.dumps(r,indent=2),encoding='utf-8')
 r=json.loads(path.read_text(encoding='utf-8'))
 print('Status:',r['status']);print('Report:',path)
 subprocess.Popen(['notepad.exe',str(path)])
 return 0 if r['status']=='passed_reforming_checks' else 1

if __name__=='__main__':raise SystemExit(main())
