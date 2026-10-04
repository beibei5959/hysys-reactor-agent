"""Fixed reference case built from scratch using remotely verified V15 APIs."""
import json
import math
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path

COMPONENTS = ['Toluene', 'Benzene', 'o-Xylene', 'm-Xylene', 'p-Xylene']
def close_enough(a, b, tolerance=1e-7):
    return math.isfinite(float(a)) and abs(float(a)-float(b)) <= tolerance

def read_stream(stream, names):
    result = {
        'temperature_K': float(stream.Temperature.GetValue('K')),
        'pressure_kPa': float(stream.Pressure.GetValue('kPa')),
        'mass_flow_kg_h': float(stream.MassFlow.GetValue('kg/h')),
        'molar_flow_kmol_h': float(stream.MolarFlow.GetValue('kgmole/h')),
    }
    if not all(math.isfinite(v) for v in result.values()):
        raise ValueError('Non-finite stream result')
    if result['temperature_K'] <= 0 or result['pressure_kPa'] <= 0:
        raise ValueError('Invalid temperature or pressure')
    if result['mass_flow_kg_h'] < 0 or result['molar_flow_kmol_h'] < 0:
        raise ValueError('Negative or undefined flow')
    # Zero flow contributes no product; ignore its arbitrary composition.
    if result['molar_flow_kmol_h'] == 0:
        result['mole_fractions'] = None
        result['component_flow_kmol_h'] = dict.fromkeys(names, 0.0)
        return result
    fractions = [float(v) for v in stream.ComponentMolarFractionValue]
    if len(fractions) != len(names):
        raise ValueError('Component names and fraction array length do not match')
    if any(not math.isfinite(v) or v < 0 or v > 1 for v in fractions):
        raise ValueError('Invalid mole fractions')
    if not math.isclose(sum(fractions), 1.0, abs_tol=1e-6):
        raise ValueError('Mole fractions do not sum to one')
    result['mole_fractions'] = dict(zip(names, fractions))
    result['component_flow_kmol_h'] = {
        n: v * result['molar_flow_kmol_h'] for n, v in zip(names, fractions)
    }
    return result


def calculate_checks(feed, products, names, reactor_valid):
    inlet = feed['component_flow_kmol_h']
    outlet = {n: sum(p['component_flow_kmol_h'][n] for p in products) for n in names}
    if inlet['Toluene'] <= 0:
        raise ValueError('No inlet toluene; conversion is undefined')
    reacted = inlet['Toluene'] - outlet['Toluene']
    conversion = reacted / inlet['Toluene']
    extent = reacted / 2
    residuals = {
        'benzene': outlet['Benzene'] - inlet['Benzene'] - extent,
        'ortho_xylene': outlet['o-Xylene'] - inlet['o-Xylene'] - extent,
        'meta_xylene': outlet['m-Xylene'] - inlet['m-Xylene'],
        'para_xylene': outlet['p-Xylene'] - inlet['p-Xylene'],
    }
    mass_out = sum(p['mass_flow_kg_h'] for p in products)
    mass_residual = mass_out - feed['mass_flow_kg_h']
    # Match the current simplified ortho-only manual reference, not all exam cases.
    molar_tolerance = max(1e-6, feed['molar_flow_kmol_h'] * 1e-4)
    checks = {
        'target_reactor_valid': reactor_valid,
        'feed_mass_1000_kg_h': abs(feed['mass_flow_kg_h'] - 1000) <= 0.01,
        'mass_balance': abs(mass_residual) <= 0.01,
        'toluene_conversion_50_percent': abs(conversion - 0.5) <= 1e-4,
        'reference_stoichiometry': all(abs(v) <= molar_tolerance for v in residuals.values()),
    }
    return {
        'conversion_fraction_from_flows': conversion,
        'conversion_percent_from_flows': conversion * 100,
        'outlet_component_flow_kmol_h': outlet,
        'mass_balance_residual_kg_h': mass_residual,
        'stoichiometry_residuals_kmol_h': residuals,
        'tolerances': {'mass_kg_h': 0.01, 'conversion_fraction': 1e-4, 'stoichiometry_kmol_h': molar_tolerance},
        'checks': checks,
        'all_checks_passed': all(checks.values()),
    }



def describe_com(obj):
    """Inspect declared members without invoking property getters."""
    info = obj._oleobj_.GetTypeInfo()
    attr = info.GetTypeAttr()
    # Use the named pywin32 TYPEATTR field, as in the successful metadata probe.
    # Tuple slot 8 is not the function count and previously truncated the list.
    result = {'interface': info.GetDocumentation(-1)[0],
              'declared_function_count': int(attr.cFuncs), 'members': []}
    for index in range(attr.cFuncs):
        desc = info.GetFuncDesc(index)
        names = info.GetNames(desc[0])
        if names:
            result['members'].append({'name': names[0], 'invkind': desc[4],
                                      'parameter_count': len(desc[2]),
                                      'documentation': info.GetDocumentation(desc[0])[1]})
    return result


def component_name(obj, evidence, depth=0):
    """Use the observed Reactant.Component.Name and Component.Name interfaces."""
    if isinstance(obj, str):
        if obj in COMPONENTS:
            return obj
        raise ValueError('Unexpected component name: ' + repr(obj))
    schema = describe_com(obj)
    kind = schema['interface']
    if kind == 'Reactant':
        name = str(obj.Component.Name)
        path = 'Reactant.Component.Name'
    elif kind == 'Component':
        name = str(obj.Name)
        path = 'Component.Name'
    else:
        evidence.append(schema)
        raise RuntimeError('Unsupported component wrapper: ' + str(kind))
    if name not in COMPONENTS:
        raise ValueError('Unexpected component name: ' + repr(name))
    evidence.append({'interface': kind, 'read_path': path, 'component_name': name})
    return name


def validate_stoichiometry(stoich):
    # Same order of numerical tolerance as the existing reference-flow checks.
    # Preserve the actual reference coefficients; never round the model inputs.
    expected = {'Toluene': -2.0, 'Benzene': 1.0, 'o-Xylene': 1.0}
    tolerance = 1e-4
    return set(stoich) == set(expected) and all(
        close_enough(stoich[n], expected[n], tolerance) for n in expected)


# Frozen from the remotely verified V15 reference, not fetched from an open case.
REFERENCE_SETTINGS = {'reaction_type': 'conversionrxn', 'set_type': 'rxnset', 'reactor_type': 'conversionreactorop', 'reactants': ['Toluene', 'Benzene', 'o-Xylene'], 'stoichiometry': [-2.0, 1.0, 1.0000527473538292], 'conversion_coefficients': [50.0, 0.0, 0.0], 'phase': 5, 'base_component': 'Toluene', 'heat_flow_kJ_h': 0.0, 'pressure_drop_kPa': 0.0, 'product_temperatures_K': {'LIQUID_PROD': 649.3400366698161, 'PRODUCT': 649.3400366698161}}

def create_feed(case, report, array, pump):
    solver = case.Solver
    previous = bool(solver.CanSolve)
    try:
        solver.CanSolve = False
        feed = case.Flowsheet.MaterialStreams.Add('FEED')
        feed.ComponentMolarFractionValue = array([1.0, 0.0, 0.0, 0.0, 0.0])
        feed.Temperature.SetValue(653.15, 'K')
        feed.Pressure.SetValue(2500.0, 'kPa')
        feed.MolarFlow.SetValue(10.852955420760267, 'kgmole/h')
        solver.CanSolve = True
        deadline = time.monotonic() + 30
        passing = 0
        while time.monotonic() < deadline:
            pump()
            time.sleep(.5)
            row = read_stream(feed, COMPONENTS)
            checks = {
                'temperature': close_enough(row['temperature_K'], 653.15, .01),
                'pressure': close_enough(row['pressure_kPa'], 2500, .01),
                'mass_flow': close_enough(row['mass_flow_kg_h'], 1000, .01),
                'molar_flow': close_enough(row['molar_flow_kmol_h'], 10.852955420760267, 1e-7),
                'composition': row['mole_fractions'] is not None and all(
                    close_enough(row['mole_fractions'][n], float(n == 'Toluene'), 1e-8) for n in COMPONENTS),
            }
            report['feed_creation_checks'] = checks
            passing = passing + 1 if all(checks.values()) else 0
            if passing >= 3:
                return feed
        raise RuntimeError('New feed checks did not pass; reactor construction stopped.')
    finally:
        solver.CanSolve = previous


def execute(app, root, report, array, pump):
    settings = dict(REFERENCE_SETTINGS)
    report['reference_settings'] = settings
    report['reference_source'] = 'Frozen settings from verified Agent run automatic-reference-integration-v1; no reference HSC read'
    report['full_model_from_scratch'] = True
    report['requires_saved_feed_case'] = False
    folder = Path(root) / 'generated_cases'
    folder.mkdir(exist_ok=True)
    destination = folder / ('toluene_from_scratch_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.hsc')
    report['working_case_file'] = str(destination)
    if destination.exists():
        raise FileExistsError('Output already exists; no case created.')
    report['stage'] = 'identify_existing_cases'
    cases = app.SimulationCases
    old_ids = {str(c.UniqueID) for c in cases}
    before_count = int(cases.Count)
    report['existing_case_count'] = before_count
    report['stage'] = 'create_case'
    report['case_creation_attempted'] = True
    case = cases.Add()
    if case is None:
        raise RuntimeError('SimulationCases.Add returned no case. No existing case will be used.')
    new_id = str(case.UniqueID)
    report['case_unique_id'] = new_id
    if not new_id or new_id in old_ids or int(cases.Count) != before_count + 1:
        raise RuntimeError('Could not verify an independent new case. Stopping before configuration.')
    report['independent_case_verified'] = True
    report['stage'] = 'show_case'
    case.Visible = True
    case.Activate()
    basis = case.BasisManager
    report['stage'] = 'start_basis_change'
    basis.StartBasisChange()
    # On failure leave only this NEW case for inspection; do not try to commit
    # incomplete changes, close cases, discard data, or run alternative APIs.
    report['stage'] = 'create_component_list'
    comp_list = basis.ComponentLists.Add('Components-AI')
    if comp_list is None:
        raise RuntimeError('ComponentLists.Add returned no component list.')
    for name in COMPONENTS:
        report['stage'] = 'add_component:' + name
        comp_list.Components.Add(name)
        actual = [str(c.Name) for c in comp_list.Components]
        report['components_after_last_add'] = actual
        if name not in actual:
            raise RuntimeError('Component was not found after Add: ' + name)
    if actual != COMPONENTS:
        raise RuntimeError('Actual component list/order differs from the requested list.')
    report['stage'] = 'create_fluid_package'
    fp = basis.FluidPackages.Add('Basis-AI')
    if fp is None:
        raise RuntimeError('FluidPackages.Add returned no fluid package.')
    report['stage'] = 'associate_component_list'
    fp.ComponentList = comp_list
    report['stage'] = 'set_property_package'
    # Remote V15 verified: setter PengRob, getter Peng-Robinson.
    report['property_package_requested_internal_name'] = 'PengRob'
    fp.PropertyPackageName = 'PengRob'
    actual_method = str(fp.PropertyPackageName)
    report['property_package_readback'] = actual_method
    if actual_method.replace('-', '').replace(' ', '').lower() != 'pengrobinson':
        raise RuntimeError('Property package readback mismatch.')
    report['stage'] = 'associate_flowsheet'
    case.Flowsheet.FluidPackage = fp
    report['stage'] = 'validate_basis'
    report['can_end_basis_change'] = bool(basis.CanEndBasisChange)
    if not report['can_end_basis_change']:
        raise RuntimeError('HYSYS reports insufficient basis information; new case left open for inspection.')
    report['stage'] = 'end_basis_change'
    basis.EndBasisChange()
    report['stage'] = 'verify_flowsheet_basis'
    active_fp = case.Flowsheet.FluidPackage
    report['flowsheet_components'] = [str(c.Name) for c in active_fp.Components]
    report['flowsheet_property_package'] = str(active_fp.PropertyPackageName)
    if report['flowsheet_components'] != COMPONENTS:
        raise RuntimeError('Flowsheet components mismatch after basis change.')
    if report['flowsheet_property_package'].replace('-', '').replace(' ', '').lower() != 'pengrobinson':
        raise RuntimeError('Flowsheet property package mismatch after basis change.')
    fs = case.Flowsheet
    fp = fs.FluidPackage
    names = [str(c.Name) for c in fp.Components]
    if int(fs.Operations.Count) or int(fs.MaterialStreams.Count):
        raise RuntimeError('Expected a new empty flowsheet.')
    report['stage'] = 'create_and_verify_feed'
    feed = create_feed(case, report, array, pump)
    report['feed_before'] = read_stream(feed, names)
    solver = case.Solver
    previous = bool(solver.CanSolve)
    try:
        report['stage'] = 'hold_solver'
        solver.CanSolve = False
        report['stage'] = 'start_reaction_basis_change'
        basis.StartBasisChange()
        report['model_write_attempted'] = True
        rpm = basis.ReactionPackageManager
        report['stage'] = 'create_conversion_reaction'
        reaction = rpm.Reactions.Add('Rxn-AI', settings['reaction_type'])
        report['stage'] = 'add_reaction_components'
        for name in settings['reactants']:
            reaction.Reactants.Add(name)
        actual_reactants = list(reaction.Reactants)
        evidence = report.setdefault('component_name_interfaces', [])
        actual_order = [component_name(c, evidence) for c in actual_reactants]
        if set(actual_order) != set(settings['reactants']) or len(actual_order) != 3:
            raise RuntimeError('Reaction component readback mismatch.')
        stoich = dict(zip(settings['reactants'],settings['stoichiometry']))
        report['stage'] = 'set_stoichiometry'
        for entry, name in zip(actual_reactants, actual_order):
            entry.StoichiometricCoefficientValue = stoich[name]
        report['stage'] = 'set_conversion_basis'
        reaction.BaseComponent = actual_reactants[actual_order.index('Toluene')].Component
        reaction.ReactionPhase = settings['phase']
        reaction.ConversionCoefficientsValue = array(settings['conversion_coefficients'])
        got = [float(entry.StoichiometricCoefficientValue) for entry in actual_reactants]
        conv = list(reaction.ConversionCoefficientsValue)
        if len(got)!=3 or not all(close_enough(v,stoich[n]) for n,v in zip(actual_order,got)):
            raise RuntimeError('Stoichiometry readback failed.')
        if len(conv)!=3 or not all(close_enough(a,b) for a,b in zip(conv,settings['conversion_coefficients'])):
            raise RuntimeError('Conversion coefficient readback failed.')
        report['stage'] = 'create_reaction_set'
        rs = rpm.ReactionSets.Add('Set-AI')
        rs.ActiveReactions.Add('Rxn-AI')
        report['stage'] = 'associate_reaction_set'
        rs.AssociateFluidPackage(fp)
        if [str(r.Name) for r in rs.ActiveReactions] != ['Rxn-AI']:
            raise RuntimeError('Active reaction set membership mismatch.')
        if not bool(basis.CanEndBasisChange):
            raise RuntimeError('HYSYS cannot finish the reaction basis.')
        report['stage'] = 'end_basis_change'
        basis.EndBasisChange()
        report['stage'] = 'create_products_and_reactor'
        vapour = fs.MaterialStreams.Add('PRODUCT')
        liquid = fs.MaterialStreams.Add('LIQUID_PROD')
        reactor = fs.Operations.Add('CRV-100', settings['reactor_type'])
        report['stage'] = 'connect_reactor'
        reactor.Feeds.Add(feed)
        reactor.VapourProduct = vapour
        reactor.LiquidProduct = liquid
        reactor.ReactionSet = rs
        report['stage'] = 'set_reactor_conditions'
        reactor.PressureDrop.SetValue(0.0, 'kPa')
        # V15 rejected a HeatFlow write on this newly built reactor. Keep its
        # unconnected-energy configuration and require zero duty AND reference
        # outlet temperatures after solving. Do not claim a specified duty.
        report['thermal_configuration'] = {
            'energy_stream_created': False,
            'heat_flow_write_attempted': False,
            'mode': 'Use newly created reactor configuration; verify zero duty and reference outlet temperatures after solve',
            'required_heat_flow_kJ_h': 0.0,
        }
        if [str(s.Name) for s in reactor.AttachedFeeds] != ['FEED'] or {str(s.Name) for s in reactor.AttachedProducts} != {'PRODUCT','LIQUID_PROD'}:
            raise RuntimeError('Reactor connection readback failed.')
        report['stage'] = 'solve_and_verify'
        solver.CanSolve = True
        deadline = time.monotonic()+45
        stable = 0
        while time.monotonic()<deadline:
            pump()
            time.sleep(1)
            try:
                streams = {str(s.Name):read_stream(s,names) for s in [feed,vapour,liquid]}
                verification = calculate_checks(streams['FEED'], [streams['PRODUCT'],streams['LIQUID_PROD']], names, bool(reactor.IsValid))
                actual_duty = float(reactor.HeatFlow.GetValue('kJ/h'))
                report['thermal_configuration']['actual_heat_flow_kJ_h'] = actual_duty
                verification['checks']['zero_heat_duty'] = close_enough(actual_duty,0,.01)
                verification['checks']['reference_outlet_temperatures'] = all(
                    close_enough(streams[n]['temperature_K'], settings['product_temperatures_K'][n], .02)
                    for n in ['PRODUCT', 'LIQUID_PROD'])
                verification['checks']['outlet_pressure'] = all(close_enough(streams[n]['pressure_kPa'],2500,.1) for n in ['PRODUCT','LIQUID_PROD'])
                verification['all_checks_passed'] = all(verification['checks'].values())
                report['streams'] = streams
                report['verification'] = verification
                stable = stable+1 if verification['all_checks_passed'] else 0
            except Exception:
                stable = 0
                report['last_poll_error'] = traceback.format_exc()
            if stable>=3:
                report['consecutive_passing_samples']=stable
                break
        else:
            raise RuntimeError('Result checks did not pass within 45 seconds. Inspect the report.')
    finally:
        # Incomplete basis can prohibit solver writes. Preserve both errors.
        try:
            solver.CanSolve=previous
        except Exception:
            report['solver_restore_error']=traceback.format_exc()
    if 'solver_restore_error' in report:
        raise RuntimeError('Could not restore solver state.')
    report['stage']='save_verified_model'
    # Save only the independently created case, without overwriting any file.
    if destination.exists():
        raise FileExistsError('Output collision; refusing to overwrite.')
    case.SaveAs2(str(destination), False)
    if not destination.is_file() or destination.stat().st_size==0:
        raise RuntimeError('Verified model file missing after save.')
    report['saved_verified_model']=str(destination)
    report['status']='passed_automatic_reference_model_checks'
    report['stage']='finished'


def main():
    root=Path(__file__).resolve().parent
    report={'script_version':'6-from-scratch','source':'hysys','status':'failed','stage':'connect',
            'scope':'Full new-case construction of fixed ortho-only zero-duty reference; not complete exam validation',
            'model_write_attempted':False}
    initialized=False
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize();initialized=True
        app=win32com.client.GetActiveObject('HYSYS.Application')
        array=lambda values:win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,values)
        print('Building real reference reactor. Keep HYSYS open; report opens automatically.',flush=True)
        execute(app,root,report,array,pythoncom.PumpWaitingMessages)
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        if initialized:pythoncom.CoUninitialize()
    folder=root/'diagnostics';folder.mkdir(exist_ok=True)
    path=folder/('hysys_unified_model_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print('Status:',report['status']);print('Stage:',report['stage']);print('Report:',path)
    if report['status']=='failed':
        print('New case may be incomplete and unsaved. Send this report before retrying.')
    try:subprocess.Popen(['notepad.exe',str(path)])
    except OSError:pass
    return 0 if report['status']=='passed_automatic_reference_model_checks' else 1

if __name__=='__main__':
    raise SystemExit(main())
