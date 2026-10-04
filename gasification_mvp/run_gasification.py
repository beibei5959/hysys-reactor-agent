"""One genuine HYSYS Gibbs-reactor coal-slurry gasification case. No LLM yet.

MVP minimal verification, assumptions agreed with the user (mirrors Codex plan):
coal = pure solid carbon; slurry = 62 wt% C + 38 wt% water; 1000 kg/h slurry;
40 bar absolute; feed 40 C; outlet 1400 C. 80000 Nm3/h is NOT used as basis.
Candidate species C(s)/H2O/CO/CO2/H2 (methanation excluded, see assumptions).
Pattern copied from the verified reforming_mvp/run_reforming.py (build/verify
phases, strict checks, three consecutive stable passes, then SaveAs).
"""
import json, math, subprocess, sys, time, traceback
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CARBON_CANDIDATES=['Carbon','C(s)','Carbon(s)','C']
REST=['H2O','CO','CO2','Hydrogen']
M_C=12.011; M_W=18.015
FEED_MASS=1000.0; W_C=0.62; W_W=0.38
NC=FEED_MASS*W_C/M_C; NW=FEED_MASS*W_W/M_W; NTOT=NC+NW
T_FEED=313.15; P_KPA=4000.0; T_OUT=1673.15

def is_carbon(name): return name in CARBON_CANDIDATES

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

def checks(feed,vap,liq,names,valid):
    out={n:vap['component_flow_kmol_h'][n]+liq['component_flow_kmol_h'][n] for n in names}
    cC=[n for n in names if is_carbon(n)][0]
    c_in=feed['component_flow_kmol_h'][cC]; w_in=feed['component_flow_kmol_h']['H2O']
    c_out=out[cC]; co=out['CO']; co2=out['CO2']; h2=out['Hydrogen']; w_out=out['H2O']
    mass=abs(feed['mass_flow_kg_h']-vap['mass_flow_kg_h']-liq['mass_flow_kg_h'])
    conv=1.-c_out/c_in if c_in>0 else -1.
    co_yield=co/c_in if c_in>0 else -1.
    el_c=abs(c_in-(c_out+co+co2))
    el_h=abs(2*w_in-(2*w_out+2*h2))
    el_o=abs(w_in-(w_out+co+2*co2))
    tol=max(.05,feed['mass_flow_kg_h']*1e-4)
    t_out_ok=abs(vap['temperature_K']-T_OUT)<.02 and (liq['molar_flow_kmol_h']<1e-8 or abs(liq['temperature_K']-T_OUT)<.02)
    tests={
     'reactor_valid':bool(valid),
     'feed_temperature':abs(feed['temperature_K']-T_FEED)<.02,
     'feed_pressure':abs(feed['pressure_kPa']-P_KPA)<.1,
     'feed_components':abs(c_in-NC)<.05 and abs(w_in-NW)<.05 and all(abs(feed['component_flow_kmol_h'][n])<1e-6 for n in REST[1:]),
     'outlet_temperature':t_out_ok,
     'outlet_pressure':abs(vap['pressure_kPa']-P_KPA)<.1 and (liq['molar_flow_kmol_h']<1e-8 or abs(liq['pressure_kPa']-P_KPA)<.1),
     'mass_balance':mass<tol,
     'element_balance':el_c<.05 and el_h<.05 and el_o<.05,
     'positive_reaction':co>0 and h2>0,
     'carbon_conversion_in_range':0.<conv<1.,
     'solid_carbon_remaining':c_out>0.,
     'co_dominant_over_co2':co>co2}
    return dict(checks=tests,all_checks_passed=all(tests.values()),carbon_conversion_percent=100.*conv,
      co_yield_percent=100.*co_yield,mass_residual_kg_h=mass,element_residuals_kmol_h=dict(C=el_c,H=el_h,O=el_o),
      outlet_component_flow_kmol_h=out)

def pick_carbon(cl):
    for cand in CARBON_CANDIDATES:
        before=cl.Components.Count
        try: cl.Components.Add(cand)
        except Exception: continue
        if cl.Components.Count==before+1 and str(cl.Components.Item(before).Name)==cand: return cand
        raise RuntimeError('Carbon component added but readback mismatch: '+cand)
    raise RuntimeError('No solid carbon component accepted; tried '+str(CARBON_CANDIDATES))

def build(app,r,array):
    cases=app.SimulationCases;old={str(c.UniqueID) for c in cases}
    r['stage']='create_independent_case'
    case=cases.Add();identity=str(case.UniqueID)
    if identity in old:raise RuntimeError('Independent case not created')
    r['case_unique_id']=identity;case.Visible=True;case.Activate()
    b=case.BasisManager;fs=case.Flowsheet
    r['stage']='create_basis';b.StartBasisChange()
    cl=b.ComponentLists.Add('Gasification-Components')
    carbon=pick_carbon(cl);r['carbon_component_name']=carbon
    for n in REST:cl.Components.Add(n)
    names=[carbon]+REST
    if [str(c.Name) for c in cl.Components]!=names:raise RuntimeError('Component name/order mismatch')
    fp=b.FluidPackages.Add('Gasification-PR');fp.ComponentList=cl;fp.PropertyPackageName='PengRob';fs.FluidPackage=fp
    if str(fp.PropertyPackageName)!='Peng-Robinson':raise RuntimeError('Property method mismatch')
    if not b.CanEndBasisChange:raise RuntimeError('Basis incomplete')
    b.EndBasisChange()
    r['names']=names
    solver=case.Solver;previous=bool(solver.CanSolve)
    try:
        solver.CanSolve=False
        r['stage']='create_reactor'
        feed=fs.MaterialStreams.Add('SLURRY')
        feed.Temperature.SetValue(T_FEED,'K');feed.Pressure.SetValue(P_KPA,'kPa')
        feed.ComponentMolarFractionValue=array([NC/NTOT]+[NW/NTOT]+[0.]*(len(names)-2))
        feed.MolarFlow.SetValue(NTOT,'kgmole/h')
        vap=fs.MaterialStreams.Add('VAP');liq=fs.MaterialStreams.Add('LIQ')
        energy=fs.EnergyStreams.Add('Q-GR')
        op=fs.Operations.Add('GR-1','gibbsreactorop')
        r['reactor_type']=str(op.TypeName)
        op.Feeds.Add(feed);op.VapourProduct=vap;op.LiquidProduct=liq;op.EnergyStream=energy
        op.PressureDrop.SetValue(0.,'kPa')
        r['stage']='specify_outlet_temperature'
        vap.Temperature.SetValue(T_OUT,'K')
    finally:solver.CanSolve=previous
    if not previous:case.Solver.CanSolve=True
    r['status']='awaiting_verification';r['stage']='build_process_finished'

def verify(app,r):
    identity=r['case_unique_id'];matches=[c for c in app.SimulationCases if str(c.UniqueID)==identity]
    if len(matches)!=1:raise RuntimeError('Exact built case not found')
    case=matches[0];fs=case.Flowsheet
    names=[str(c.Name) for c in fs.FluidPackage.Components]
    if names!=r.get('names'):raise RuntimeError('Wrong component order')
    stable=0;prev=None;r['stage']='verify_1400C';deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        time.sleep(2)
        try:
            sol=case.Solver;idle=bool(sol.CanSolve) and not bool(sol.IsSolving) and not bool(sol.IsForgetting)
            r['solver_idle_observed']=idle
            op=fs.Operations.Item('GR-1')
            feed=read_stream(fs.MaterialStreams.Item('SLURRY'),names)
            vap=read_stream(fs.MaterialStreams.Item('VAP'),names);liq=read_stream(fs.MaterialStreams.Item('LIQ'),names)
            result=checks(feed,vap,liq,names,op.IsValid)
            result['checks']['reactor_not_ignored']=not bool(op.IsIgnored)
            flow=result['outlet_component_flow_kmol_h']
            result['checks']['results_stable']=prev is not None and max(abs(flow[n]-prev[n]) for n in flow)<1e-6
            result['all_checks_passed']=all(result['checks'].values())
            result.update(feed=feed,vapour_product=vap,liquid_product=liq,
              heat_duty_kJ_h=finite(op.HeatFlow.GetValue('kJ/h')),reactor_type=str(op.TypeName))
            r['results']={'1400':result}
            good=result['all_checks_passed']
            stable=stable+1 if good else 0
            prev=flow
            if stable>=3:break
        except Exception:
            stable=0;r['last_poll_error']=traceback.format_exc()
    else:raise RuntimeError('Gasification verification did not pass. Inspect results; no success claimed.')
    r['stage']='save_verified_case'
    path=Path(r['planned_case_file'])
    if path.exists():raise FileExistsError(path)
    case.SaveAs2(str(path),False)
    if not path.is_file() or path.stat().st_size==0:raise RuntimeError('Saved file missing')
    r.update(status='passed_gasification_checks',stage='finished',saved_case=str(path),consecutive_passing_samples=stable)

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
    return 0 if r['status'] in ['awaiting_verification','passed_gasification_checks'] else 1

def main():
    if len(sys.argv)==3:return worker(sys.argv[1],Path(sys.argv[2]))
    folder=ROOT/'diagnostics';folder.mkdir(exist_ok=True)
    generated=ROOT/'generated_cases';generated.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f');path=folder/('gasification_'+stamp+'.json')
    r=dict(source='hysys',status='not_started',stage='start',
      scope='MVP automatic Gibbs coal-slurry gasification; no natural-language integration yet',
      assumptions=['Coal modelled as pure solid carbon; slurry 62 wt% C + 38 wt% water; 1000 kg/h slurry = {nc:.4f} kmol/h C + {nw:.4f} kmol/h H2O'.format(nc=NC,nw=NW),
       '40 bar interpreted as absolute (4000 kPa); zero pressure drop; feed 40 C; outlet 1400 C specified on vapour product',
       'Candidate species C(s)/H2O/CO/CO2/H2; Gibbs free-energy minimisation covers main C+H2O=CO+H2 plus WGS and Boudouard as emergent side reactions; methanation excluded because CH4 equilibrium share is small at 1400 C and its inclusion trapped the HYSYS Gibbs solver in a non-physical local solution - documented MVP simplification',
       'No oxidant (O2) feed modelled: problem statement lists slurry and water only, so carbon conversion is steam-limited and unreacted solid carbon is expected',
       '80000 Nm3/h not used as an absolute basis; results reported per 1000 kg/h slurry'],
      planned_case_file=str(generated/('gasification_'+stamp+'.hsc')))
    path.write_text(json.dumps(r,indent=2),encoding='utf-8')
    try:
        for phase in ['build','verify']:
            print('HYSYS phase:',phase,flush=True)
            p=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),phase,str(path)],timeout=660)
            if p.returncode!=0:break
    except Exception:
        r=json.loads(path.read_text(encoding='utf-8'));r.update(status='outcome_unknown',controller_error=traceback.format_exc())
        path.write_text(json.dumps(r,indent=2),encoding='utf-8')
    r=json.loads(path.read_text(encoding='utf-8'))
    print('Status:',r['status']);print('Report:',path)
    subprocess.Popen(['notepad.exe',str(path)])
    return 0 if r['status']=='passed_gasification_checks' else 1

if __name__=='__main__':raise SystemExit(main())
