from dataclasses import dataclass

import pandas as pd
import numpy as np
import cvxpy as cp
import zipfile
import time

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .core import CarbonTracer
    from .grid import PowerFlowResults, PowerFlowCalculator


def carrierinit(tracer: "CarbonTracer") -> pd.DataFrame:
    """
    Initialize the carbon carrier intensity data for the given tracer.

    Parameters
    ---
    tracer : CarbonTracer
        The carbon tracer object.

    Returns
    ----
    pd.DataFrame
        A DataFrame containing the initialized carbon carrier intensity data.
    """
    #source pour l'intenité carbone du pv:
    #https://www.enerplan.asso.fr/analyse-de-l-impact-climat-de-capacites-additionnelles-solaires-photovoltaiques-en-france-a-horizon-2030-avril-2020
    
    # Path to the ZIP file
    zip_path = tracer.path_dict['ci_cantons']

    selected_canton = tracer.canton_located
    snapshots = tracer.snapshots

    with zipfile.ZipFile(zip_path, 'r') as z:
        # List all files in the ZIP archive
        file_list = z.namelist()
        
        # Find the file for the selected canton
        selected_file = next((f for f in file_list if f"ci_{selected_canton}.csv" in f), None)
        
        if selected_file:
            # Read the CSV file into a pandas DataFrame
            with z.open(selected_file) as file:
                ci_df = pd.read_csv(file, index_col=0)# gCO2eq/kWh
            ci_df.index = pd.to_datetime(ci_df.index).tz_localize(tz = 'Etc/GMT-1').tz_convert(snapshots.tz)
            print(f"HV carbon intensity data for canton {selected_canton} loaded.")
        else:
            print(f"No CSV file found for canton {selected_canton}.")

    ci_df = ci_df.loc[snapshots]
    ci_df.columns = ['HV Grid']
    ci_df['Photovoltaic']= 30 # gCO2eq/kWh    
    ci_df['Wind energy'] = 13
    ci_df['Hydroelectric power'] = 11
    ci_df['Nuclear energy'] = 5
    ci_df['Natural gas'] = 528
    ci_df['Coal'] = 1187
    ci_df['Crude oil'] = 1170
    ci_df['Biomass'] = 230
    ci_df['Geothermal'] = 38
    return ci_df

# TODO: Introduce Sparse

def create_array(indices, values, shape=None) -> np.ndarray:
    """
    Create a vector or matrix based on given indices and values,
    filling non-mentioned elements with 0.
    
    Parameters
    ---
    indices : list or array
        1D (for a vector) or 2D (for a matrix) indices.

        - Example (1D): [0, 2, 3]
        - Example (2D): [(0, 1), (1, 2), (2, 0)]
    values : list or array
        Values corresponding to the indices.

        - Example: [5, 10, 15]
    shape : tuple, optional
        Shape of the resulting array. If not provided, the shape is inferred.


    Returns
    ---
    np.ndarray
        A numpy array (vector or matrix) with the specified values and zeros elsewhere.
    """
    indices = np.array(indices)
    values = np.array(values)
    
    # Automatically determine the shape if not provided
    if shape is None:
        if indices.ndim == 1:  # For 1D indices (vector)
            shape = (indices.max() + 1,)
        elif indices.ndim == 2:  # For 2D indices (matrix)
            shape = (indices[:, 0].max() + 1, indices[:, 1].max() + 1)
    
    # Initialize the array with zeros
    array = np.zeros(shape, dtype=values.dtype)
    
    # Assign values at the specified indices
    if indices.ndim == 1:  # 1D case
        array[indices] = values
    elif indices.ndim == 2:  # 2D case
        array[indices[:, 0], indices[:, 1]] = values
    
    return array


def _calculate_qin(G_L: np.ndarray, Pin: np.ndarray, I: np.ndarray) -> np.ndarray:
    """
    Calculate the qin matrix based on the given formula.

    Parameters
    ---
    G_L : np.ndarray
        Generation minus Load values (1D array).
    Pin : np.ndarray
        Pin values (1D array).
    I : np.ndarray
        Import values (1D array).
    
    Returns
    ----
    np.ndarray
        The qin matrix calculated based on the formula:
        qin = [diag(G_L/Pin), I/Pin]

    """
    
    qin_left = np.diag([G_L[i] / Pin[i] if G_L[i] != 0 else 0 for i in range(len(G_L))])
    qin_right = np.array([[I[i] / Pin[i] if I[i] != 0 else 0 for i in range(len(G_L))]])
    return np.concatenate((qin_left, qin_right.T),axis=1)

def calculate_Q(G: np.ndarray, L: np.ndarray, I: np.ndarray, X: np.ndarray, FF: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Calculate the Q matrix based on the given formula.

    Parameters
    ---
    G : np.ndarray 
        Generation values (1D array).

    L : np.ndarray
        Load values (1D array).
    I : np.ndarray
        Import values (1D array).
    X : np.ndarray
        Export values (1D array).
    FF : np.ndarray
        Flow values (2D array). 

    Returns
    ----
    tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        A tuple containing the following elements:
        - q
        - Fin
        - Fout
        - Pout
    """
    G_L = np.maximum((G-L),0)

    # def Pin Pout qin
    Pin = np.maximum((G-L),0) + I
    Pout = np.maximum(-(G-L),0) + X
    qin = _calculate_qin(G_L, Pin, I)

    Fout = np.where(FF>=0, FF, 0)
    Fin = - np.where(FF<=0, FF, 0)
    
    F = Pout + Fout @ np.ones(len(G_L))
    
    D = (Fin.T/(F)).T
    # q = np.linalg.inv(np.eye(len(G_L))-D) @ np.diag(Pin/F) @ qin
    q = np.linalg.solve(np.diag(F) -Fin, (np.diag(Pin)@qin))
    
    
    return q, Fin, Fout, Pout


def _calculate_carrier_for_merged_plants(group, p_mw_df, ci_df, plant_df):
    """
    A helper function to calculate the carbon carrier intensity for merged plants, if more than one plant is attributed to the same bus, based on their power generation and individual carbon intensities.

    Returns
    ---
    pd.Series
        A Series containing the calculated carbon carrier intensity for the merged plants at the bus.
    """
    gen_idx = group.index
    power_gens = p_mw_df[gen_idx]
    merged_power = power_gens.sum(axis = 1)
    ci_gens = ci_df[plant_df.loc[gen_idx].type.values]
    ci_gens.columns = gen_idx
    merged_carbon = (power_gens*ci_gens).sum(axis = 1)
    merged_ci = (merged_carbon/merged_power).fillna(0)
    return merged_ci

def _calculate_power_for_merged_plants(group, p_mw_df):
    """
    A helper function to calculate the total power for merged plants.

    Returns
    ---
    pd.Series
        A Series containing the total power for the merged plants at the bus.
    """
    gen_idx = group.index
    power_gens = p_mw_df[gen_idx]
    merged_power = power_gens.sum(axis = 1)
    return merged_power

@dataclass
class FlowDataWrapper:
    """
    A dataclass to encapsulate all the flow data needed for carbon tracing in a single object, improving code readability and maintainability.

    Attributes
    ------
    n : int
        The number of nodes in the power grid.
    P_ij: np.ndarray
        The power flow matrix between nodes (2D array).
    G: np.ndarray
        The generation vector (1D array).
    L: np.ndarray
        The load vector (1D array).
    I: np.ndarray
        The import vector (1D array).
    X: np.ndarray
        The export vector (1D array)
    Fin: np.ndarray
        The inflow matrix (2D array).
    Fout: np.ndarray
        The outflow matrix (2D array).
    Pin: np.ndarray
        The Pin vector (1D array).
    Pout: np.ndarray
        The Pout vector (1D array).

    """
    
    n: int
    P_ij: np.ndarray
    G: np.ndarray
    L: np.ndarray
    I: np.ndarray
    X: np.ndarray
    carriers: np.ndarray
    Fin: np.ndarray
    Fout: np.ndarray
    Pin: np.ndarray
    Pout: np.ndarray





def organize_step_flow_data(pf_calculator: "PowerFlowCalculator", ci_df: pd.DataFrame, step: pd.Timestamp) -> FlowDataWrapper:
    """
    Organize the power flow data for a specific time step into a structured format (FlowDataWrapper) that can be easily used for carbon tracing calculations.
    This function extracts the necessary data from the power flow results and prepares it for the carbon tracing algorithm.

    Parameters
    ------
    pf_calculator: "PowerFlowCalculator"
        The power flow calculator object containing the power flow results and grid information.
    ci_df: pd.DataFrame
        The carbon intensity DataFrame containing the carbon intensity values for different generations / import sources.
    step: pd.Timestamp
        A timestamp. The specific time step for which the flow data is being organized.
    
    Returns
    ------
    "FlowDataWrapper"
        A FlowDataWrapper object containing all the organized flow data for the specified time step, ready to be used in carbon tracing calculations.
    """

    pp_grid = pf_calculator.pp_grid
    pf_results = pf_calculator.pf_results

    branches = list(zip(pp_grid.line.from_bus,pp_grid.line.to_bus))
    branches.extend(zip(pp_grid.trafo.hv_bus,pp_grid.trafo.lv_bus))
    branch_from_values = pf_results.p_from_mw_line_df.loc[step,:].values
    branch_from_values = np.append(branch_from_values,pf_results.p_hv_mw_trafo_df.loc[step,:].values)
    branch_to_values = pf_results.p_to_mw_line_df.loc[step,:].values
    branch_to_values = np.append(branch_to_values,pf_results.p_lv_mw_trafo_df.loc[step,:].values)

    n = len(pp_grid.bus)
    # FF = create_array(branches,branch_from_values,(n,n)) + (create_array(branches,branch_to_values,(n,n))).T
    P_ij = create_array(branches,branch_from_values,(n,n)) + (create_array(branches,branch_to_values,(n,n))).T
    
    merged_carrier_sgen = pp_grid.sgen.groupby('bus').apply(lambda x: _calculate_carrier_for_merged_plants(x, p_mw_df=pf_results.p_mw_sgen_df, ci_df=ci_df, plant_df=pp_grid.sgen), include_groups=False).T
    merged_power_sgen = pp_grid.sgen.groupby('bus').apply(lambda x: _calculate_power_for_merged_plants(x, p_mw_df=pf_results.p_mw_sgen_df), include_groups=False).T
    merged_carrier_gen = pp_grid.gen.groupby('bus').apply(lambda x: _calculate_carrier_for_merged_plants(x, p_mw_df=pf_results.p_mw_gen_df, ci_df=ci_df, plant_df=pp_grid.gen), include_groups=False).T
    merged_power_gen = pp_grid.gen.groupby('bus').apply(lambda x: _calculate_power_for_merged_plants(x, p_mw_df=pf_results.p_mw_gen_df), include_groups=False).T

    if len(pp_grid.gen) >0:
        all_gen_buses = np.append(merged_power_sgen.columns, merged_power_gen.columns)
        all_gen_mw = np.append(merged_power_sgen.loc[step].values, merged_power_gen.loc[step].values)
        all_gen_carrier =  np.append(merged_carrier_sgen.loc[step].values, merged_carrier_gen.loc[step].values)
    else :
        all_gen_buses = np.array(merged_power_sgen.columns)
        all_gen_mw = np.array(merged_power_sgen.loc[step].values)
        all_gen_carrier = np.array(merged_carrier_sgen.loc[step].values)
    

    G = create_array(all_gen_buses, all_gen_mw, shape=n)
    
    L = create_array(pp_grid.load.bus.values, pf_results.p_mw_load_df.loc[step,:].values, shape=n)
    
    slack = pf_results.p_mw_ext_grid_df.loc[step,:].values[0]
    # Warning: export......
    I = create_array(pp_grid.ext_grid.bus.values, slack, shape=n) if slack >= 0 else create_array(0,0,n)
    X = create_array(0,0,n) if slack >= 0 else create_array(pp_grid.ext_grid.bus.values, slack, shape=n)

    Pout = np.maximum(-(G-L),0) + X

    Fout = np.where(P_ij>=0, P_ij, 0)
    Fin = - np.where(P_ij<=0, P_ij, 0)

    carriers = create_array(all_gen_buses, all_gen_carrier, shape=n) + create_array(pp_grid.ext_grid.bus.values, ci_df.loc[step,'HV Grid'], shape=n)

    step_flow_data = FlowDataWrapper(
        n = n,
        P_ij = P_ij,
        G = G,
        L = L,
        I = I,
        X = X,
        carriers = carriers,
        Fin = Fin,
        Fout = Fout,
        Pin = np.maximum((G-L),0) + I,
        Pout = Pout
    )
    return step_flow_data


def post_process_carbon(tracer: "CarbonTracer") -> None:
    """
    Post-process the carbon intensity and carbon emissions data after allocation, including calculating net carbon intensity, weighted net carbon intensity, and local PV generation aggregated to a LV-net level.
    """
    node_ce_df = tracer.node_ce_df

    net_ce_df = node_ce_df.copy(deep=True)
    net_ce_df.columns = net_ce_df.columns.str.removeprefix('bus_').str.replace(r'_node_\d+$', '', regex=True)
    net_ce_df = net_ce_df.T.groupby(net_ce_df.columns).sum().T


    enduse_EL = tracer.pf_calculator.load_p_mw_t

    enduse_EL.columns = tracer.pp_grid.bus.name.loc[tracer.pp_grid.load.bus].values

    enduse_EL_by_net = enduse_EL.copy(deep=True)
    enduse_EL_by_net.columns = enduse_EL_by_net.columns.str.removeprefix('bus_').str.replace(r'_node_\d+$', '', regex=True)
    enduse_EL_by_net = enduse_EL_by_net.T.groupby(enduse_EL_by_net.columns).sum().T

    weighted_net_ci_df = (net_ce_df/enduse_EL_by_net)
    hv_net_idx = tracer._raw_net_ci_df.columns[tracer._raw_net_ci_df.columns.str.contains('HV')]
    weighted_net_ci_df[hv_net_idx] = tracer._raw_net_ci_df[hv_net_idx]

    local_PV_by_net = tracer.pf_calculator.sgen_p_mw_t.rename(columns=tracer.pp_grid.sgen.bus.apply(lambda x: tracer.pp_grid.bus.name[x]))
    local_PV_by_net.columns  = local_PV_by_net.columns.str.removeprefix('bus_').str.replace(r'_node_\d+$', '', regex=True)
    local_PV_by_net = local_PV_by_net.T.groupby(local_PV_by_net.columns).sum().T
    
    tracer.net_ce_df = net_ce_df
    tracer.net_ci_df = weighted_net_ci_df
    tracer.enduse_EL_by_net = enduse_EL_by_net
    tracer.local_PV_by_net = local_PV_by_net


SOLVER_OPTS = {
    'solver': cp.HIGHS,
    'dual_feasibility_tolerance': 1e-6,
    'primal_feasibility_tolerance': 1e-6,
    'ipm_optimality_tolerance': 1e-6, # For interior point
    'verbose': False
}

def carbon_tracing_ap(step_flow_data: FlowDataWrapper, self_consumption:bool = True) -> tuple[np.ndarray, np.ndarray]:
    """
    Perform carbon tracing (average participation) using an optimization approach to calculate the carbon intensity of the ejected flow and the node emission, with an option to consider self-consumption. (LL method and LL-P method)

    Parameters
    ------
    step_flow_data : FlowDataWrapper
        A FlowDataWrapper object containing all the necessary flow data for the specific time step.
    self_consumption: bool, default True
        A boolean flag indicating whether to consider self-consumption in the carbon tracing calculation. If True, the method will prioritize the self-consumption for prosumer nodes (LL-P method), otherwise, the method will follow the perfect-mix assumption (LL method).
    
    Returns
    ------
    tuple[np.ndarray, np.ndarray]
        A tuple containing two numpy arrays:

        - `eject_intensity`: The carbon intensity of the ejected flow at each node, i.e., $c_x$ for LL method and $c_o$ for LL-P method.
        - `node_emission`: The total emission at each node, calculated as the product of the eject intensity and the load (L) at each node.

    See Also
    ------
    - [carbon.carbon_tracing_ap_with_losses](/reference/carbon.carbon_tracing_ap_with_losses.qmd)
    """

    # unpack the flow data for the step
    G = step_flow_data.G
    L = step_flow_data.L
    I = step_flow_data.I
    X = step_flow_data.X
    carriers = step_flow_data.carriers
    Fin = step_flow_data.Fin
    Fout = step_flow_data.Fout
    Pout = step_flow_data.Pout
    n = step_flow_data.n

    if self_consumption == False:
        c_x = cp.Variable(n, nonneg = True)
        obj = cp.Minimize((G+I)@carriers - (L+X)@c_x)
        con = [c_x<=max(carriers)]
        con += [(G+I)*carriers + Fin@c_x >= cp.multiply(L+X,c_x) + cp.multiply(np.sum(Fout, axis=1),c_x)]
        prob = cp.Problem(obj, con)
        prob.solve(**SOLVER_OPTS)
        assert prob.status == cp.OPTIMAL, 'The optimization problem did not solve to optimality.'
        eject_intensity = c_x.value
        node_emission = eject_intensity*L
    else:
        c_x = cp.Variable(n, nonneg = True)
        c_o = cp.Variable(n,nonneg = True)
        obj = cp.Minimize((G+I)@carriers - (L+X)@c_o)
        con = [c_x<=max(carriers)]
        con += [np.maximum((G-L),0)*carriers + I*carriers + Fin@c_x >= cp.multiply(np.maximum(-(G-L),0)+X,c_x) + cp.multiply(np.sum(Fout, axis=1),c_x)]
        con += [cp.multiply(c_o, L+X) <= cp.multiply(Pout,c_x) + cp.multiply(np.minimum(G,L),carriers)]
        prob = cp.Problem(obj, con)
        prob.solve(**SOLVER_OPTS)
        assert prob.status == cp.OPTIMAL, 'The optimization problem did not solve to optimality.'
        eject_intensity = np.where((L+X)==0, c_x.value, c_o.value)
        node_emission = eject_intensity*L

    
    return eject_intensity.round(3), node_emission.round(3)

def compare_opt_closed_formulation(step_flow_data: FlowDataWrapper):
    """
    Compare the result and runtime of the optimization-based formulation and the closed-form by directly solving the linear system for the LL method.

    Parameters
    ------
    step_flow_data : FlowDataWrapper
        A FlowDataWrapper object containing all the necessary flow data for the specific time step.
    
    Returns
    ------
    tuple[np.ndarray,np.ndarray,float,float]
        A tuple contains: the intensity of ejected flow calculated by the optimization approach, the intensity of ejected flow calculated by the closed-form approach, the runtime of the optimization approach, and the runtime of the closed-form approach.

    """

    # import scipy.sparse as sp
    # from scipy.sparse import csr_matrix, diags
    # from scipy.sparse.linalg import spsolve

    # unpack the flow data for the step
    G = step_flow_data.G
    L = step_flow_data.L
    I = step_flow_data.I
    X = step_flow_data.X
    carriers = step_flow_data.carriers
    Fin = step_flow_data.Fin
    Fout = step_flow_data.Fout
    n = step_flow_data.n

    row_sum_Fout = np.sum(Fout, axis=1)
    
    # --- 1. Optimization Approach ---
    t0 = time.perf_counter()
    c_x_opt = cp.Variable(n, nonneg=True)
    
    obj = cp.Minimize((G+I)@carriers - (L+X)@c_x_opt)
    con = [c_x_opt <= max(carriers)]
    con += [(G+I)*carriers + Fin @ c_x_opt >= cp.multiply(L+X + row_sum_Fout, c_x_opt)]
    prob = cp.Problem(obj, con)
    prob.solve(**SOLVER_OPTS)
    res_opt = c_x_opt.value
    
    t_opt = time.perf_counter() - t0

    # --- 2. Closed-Form Approach (Direct solve the linear system) ---
    t1 = time.perf_counter()
    try:
        # Construct A matrix: Diagonal (Outflows) - Off-diagonal (Inflows)
        A = np.diag(L + X + row_sum_Fout) - Fin
        b = (G + I) * carriers
        
        # Solving Ac = b using a linear solver (more stable than .inv())
        res_closed = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        res_closed = np.nan # Fails if matrix is singular (e.g., transit loops)
    
    t_closed = time.perf_counter() - t1

    return res_opt, res_closed, t_opt, t_closed




def cal_node_flow_with_losses(P_ij: np.ndarray, P_gen: np.ndarray, P_load: np.ndarray, carriers: np.ndarray):
    """
    A standard implementation of the carbon allocation with losses (LA method).

    See Also
    --------
    - [carbon.carbon_tracing_ap_with_losses](/reference/carbon.carbon_tracing_ap_with_losses.qmd)
    - [carbon.optimized_node_flow_with_losses](/reference/carbon.optimized_node_flow_with_losses.qmd)
    """

    P_gen_net = np.maximum(P_gen-P_load,0)
    P_load_net = np.maximum(-(P_gen-P_load),0)

    P_j = (np.abs(P_ij).sum(axis=1) +P_gen+P_load)/2
    alpha_u = [np.where(row < 0)[0] for row in P_ij]
    alpha_d = [np.where(row > 0)[0] for row in P_ij]

    n_node = P_ij.shape[0]

    P_node_inj = P_gen_net - P_load_net
    # n_gen = (P_node_inj>0).sum()
    # n_load = (P_node_inj<=0).sum()
    id_gen = np.where(P_node_inj>0)[0]
    id_load = np.where(P_node_inj<=0)[0]
    
    A_u = np.zeros((n_node,n_node))

    for i in range(n_node):
        for j in alpha_u[i]:
            A_u[i,j] = -P_ij[j,i]/P_j[j]
        A_u[i,i] = 1

    A_d = np.zeros((n_node,n_node))
    for i in range(n_node):
        for j in alpha_d[i]:
            A_d[i,j] = -P_ij[i,j]/P_j[j]
        A_d[i,i] = 1

    A_u_inv = np.linalg.inv(A_u)
    P_i_gross = A_u_inv@P_gen_net

    A_d_inv = np.linalg.inv(A_d)
    P_i_net = A_d_inv@P_load_net

    branch_flow_from = np.zeros((n_node,n_node))
    for k in id_gen:
        # D_G topological generation distribution factor
        D_k = np.zeros((n_node,n_node))
        for i in range(n_node):
            for j in alpha_d[i]:
                D_k[i,j] = P_ij[i,j]*A_u_inv[i,k]/P_i_gross[i]
        branch_flow_from += D_k*P_node_inj[k]* carriers[k]

    ci_ij = branch_flow_from/np.where(P_ij>0, P_ij, np.inf)
    ci_ij = ci_ij + ci_ij.T



    loss_ij = P_ij + P_ij.T
    neg_mask = np.where(P_ij < 0, P_ij, np.inf)

    surcharge = np.zeros((n_node, n_node))

    for k in id_load:
        # D_L topological load distribution factor
        scale = (A_d_inv[:, k] / P_i_net) * P_node_inj[k]   # shape (n_node,)
        D_k = P_ij * scale[:, None]                         # broadcasting
        contri_k = D_k / neg_mask
        surcharge[k] = (contri_k * loss_ij * ci_ij).sum(axis=0)


    surcharge = surcharge.sum(axis = 1)


    node_flow_without_loss = (P_ij*ci_ij).sum(axis=1)
    node_flow = node_flow_without_loss + surcharge


    flow_intensity = node_flow/np.where(P_node_inj!=0, P_node_inj, np.inf)

    id_0_nodes = np.where((np.abs(P_ij.sum(axis=1)))<=1e-8)[0]
    
    for id_0_node in id_0_nodes:
        idx_pos = np.where((P_ij[id_0_node,:])>0)[0]
        flow_intensity[id_0_node] = ((P_ij*ci_ij)[id_0_node,idx_pos]).sum() / P_ij[id_0_node,idx_pos].sum()

    node_emission = -(node_flow - P_gen*carriers)

    eject_intensity = flow_intensity.copy()
    id_prosumers = np.where((P_gen*P_load)!=0)[0]
    for id_prosumer in id_prosumers:
        if P_gen[id_prosumer]>=P_load[id_prosumer]:
            eject_intensity[id_prosumer] = carriers[id_prosumer]
        else:
            eject_intensity[id_prosumer] = node_emission[id_prosumer]/P_load[id_prosumer]


    return node_flow, flow_intensity, node_emission, eject_intensity

def carbon_tracing_ap_with_losses(step_flow_data: FlowDataWrapper, use_numba:bool = False) -> tuple[np.ndarray, np.ndarray]:
    """
    Perform carbon tracing (average participation) with the losses allocation to users. (LA method)

    Parameters
    ------
    step_flow_data : FlowDataWrapper
        A FlowDataWrapper object containing all the necessary flow data for the specific time step.
    use_numba: bool, default False
        A boolean flag indicating whether to use the numba JIT acceleration. If True, the method will call `optimized_node_flow_with_losses`, otherwise, the method will call `cal_node_flow_with_losses`.
    
    Returns
    ------
    tuple[np.ndarray, np.ndarray]
        A tuple containing two numpy arrays:

        - `eject_intensity`: The carbon intensity of the ejected flow at each node (losses allocated to users).
        - `node_emission`: The total emission at each node, calculated as the product of the eject intensity and the load (L) at each node.
    
    See Also
    --------
    - [carbon.cal_node_flow_with_losses](/reference/carbon.cal_node_flow_with_losses.qmd)
    - [carbon.optimized_node_flow_with_losses](/reference/carbon.optimized_node_flow_with_losses.qmd)
    """

    # unpack the flow data for the step
    G = step_flow_data.G
    L = step_flow_data.L
    I = step_flow_data.I
    X = step_flow_data.X
    P_ij = step_flow_data.P_ij
    carriers = step_flow_data.carriers

    P_gen = G+I

    P_load = L+X

    if use_numba:
        node_flow, flow_intensity, node_emission, eject_intensity = optimized_node_flow_with_losses(P_ij, P_gen, P_load, carriers)
    else:
        node_flow, flow_intensity, node_emission, eject_intensity = cal_node_flow_with_losses(P_ij, P_gen, P_load, carriers)

    return eject_intensity.round(3), node_emission.round(3)

_NUMBA_HELPERS = None

def _get_numba_helpers():
    """Checks for dependencies and returns compiled functions."""
    global _NUMBA_HELPERS
    if _NUMBA_HELPERS is not None:
        return _NUMBA_HELPERS

    try:
        from numba import njit, prange
        import scipy.sparse as sp
        from scipy.sparse.linalg import splu
    except ImportError:
        raise ImportError(
            "Optimization failed: 'numba' and 'scipy' are required for this function. "
            "Please install them via: pip install numba scipy"
        )

    @njit(parallel=True)
    def compute_surcharge_numba(id_load, P_ij, A_d_inv_cols, P_i_net, P_node_inj, loss_ij, ci_ij):
        """
        Eliminates the O(N^2) memory allocation of D_k and contri_k.
        Calculates the surcharge summation directly in CPU cache.
        """
        n_node = P_ij.shape[0]
        n_load = len(id_load)
        surcharge_results = np.zeros(n_node)

        for idx in prange(n_load):
            k = id_load[idx]
            # P_node_inj[k] is negative for loads, so we take abs or manage sign
            inj_k = P_node_inj[k]
            
            # Pre-calculate the scalar multiplier for this specific load k
            # scale[i] = (A_d_inv[i, k] / P_i_net[i]) * P_node_inj[k]
            scale = (A_d_inv_cols[:, idx] / P_i_net) * inj_k
            
            local_sum = 0.0
            for i in range(n_node):
                for j in range(n_node):
                    # original mask: neg_mask = np.where(P_ij < 0, P_ij, np.inf)
                    # contri_k = D_k / neg_mask => (P_ij[i,j] * scale[i]) / P_ij[i,j] = scale[i]
                    # Only valid where P_ij[i,j] < 0
                    if P_ij[i, j] < 0:
                        local_sum += scale[i] * loss_ij[i, j] * ci_ij[i, j]
            
            surcharge_results[k] = local_sum
            
        return surcharge_results

    @njit
    def assemble_coo_data(P_ij, P_j, is_upstream):
        """
        Fastest way to iterate through P_ij to find indices for Sparse Matrix.
        """
        n = P_ij.shape[0]
        rows = []
        cols = []
        data = []
        
        # Add diagonal
        for i in range(n):
            rows.append(i)
            cols.append(i)
            data.append(1.0)
            
        for i in range(n):
            for j in range(n):
                if is_upstream:
                    if P_ij[i, j] < 0: # alpha_u logic
                        rows.append(i)
                        cols.append(j)
                        data.append(-P_ij[j, i] / P_j[j])
                else:
                    if P_ij[i, j] > 0: # alpha_d logic
                        rows.append(i)
                        cols.append(j)
                        data.append(-P_ij[i, j] / P_j[j])
                        
        return np.array(rows), np.array(cols), np.array(data)


    _NUMBA_HELPERS = (compute_surcharge_numba, assemble_coo_data, splu, sp)
    return _NUMBA_HELPERS


def optimized_node_flow_with_losses(P_ij, P_gen, P_load, carriers):
    """
    Optimized version of `cal_node_flow_with_losses` using sparse matrices and Numba for performance.
    To accelerate the computation, you must have `scipy` and `numba` installed.

    See Also
    --------
    - [carbon.cal_node_flow_with_losses](/reference/carbon.cal_node_flow_with_losses.qmd)
    - [carbon.carbon_tracing_ap_with_losses](/reference/carbon.carbon_tracing_ap_with_losses.qmd)
    """

    compute_surcharge_numba, assemble_coo_data, splu, sp = _get_numba_helpers()



    n_node = P_ij.shape[0]
    
    # Basic Pre-processing
    P_gen_net = np.maximum(P_gen - P_load, 0)
    P_load_net = np.maximum(-(P_gen - P_load), 0)
    P_node_inj = P_gen_net - P_load_net
    
    P_j = (np.abs(P_ij).sum(axis=1) + P_gen + P_load) / 2.0
    # Avoid division by zero in weights
    P_j_safe = np.where(P_j == 0, np.inf, P_j)

    # 1. Build Sparse Matrices using Numba-accelerated COO assembly
    r_u, c_u, d_u = assemble_coo_data(P_ij, P_j_safe, True)
    A_u = sp.csc_matrix((d_u, (r_u, c_u)), shape=(n_node, n_node))
    
    r_d, c_d, d_d = assemble_coo_data(P_ij, P_j_safe, False)
    A_d = sp.csc_matrix((d_d, (r_d, c_d)), shape=(n_node, n_node))

    # 2. Sparse LU Factorization (Much faster than spsolve for multiple RHS)
    lu_u = splu(A_u)
    lu_d = splu(A_d)

    P_i_gross = lu_u.solve(P_gen_net)
    P_i_net = lu_d.solve(P_load_net)

    # 3. Targeted Inverse Column Extraction
    id_gen = np.where(P_node_inj > 0)[0]
    id_load = np.where(P_node_inj <= 0)[0]
    
    # Get columns of A_u_inv for generators
    I_gen = np.eye(n_node)[:, id_gen]
    A_u_inv_cols = lu_u.solve(I_gen) 

    # 4. Branch Flow Calculation (Vectorized)
    weight_vector = P_node_inj[id_gen] * carriers[id_gen]
    P_i_gross_safe = np.where(P_i_gross == 0, np.inf, P_i_gross)
    
    # Combined scale replaces the nested loop for branch_flow_from
    combined_scale = (A_u_inv_cols / P_i_gross_safe[:, None]) @ weight_vector
    branch_flow_from = np.where(P_ij > 0, P_ij * combined_scale[:, None], 0)

    # 5. Carbon Intensity and Loss setup
    ci_ij = np.zeros_like(P_ij)
    pos_mask = P_ij > 0
    ci_ij[pos_mask] = branch_flow_from[pos_mask] / P_ij[pos_mask]
    ci_ij = ci_ij + ci_ij.T
    
    loss_ij = P_ij + P_ij.T

    # 6. Surcharge Calculation (Numba Parallel)
    # Get columns of A_d_inv for loads
    I_load = np.eye(n_node)[:, id_load]
    A_d_inv_cols = lu_d.solve(I_load)
    
    P_i_net_safe = np.where(P_i_net == 0, np.inf, P_i_net)
    surcharge = compute_surcharge_numba(id_load, P_ij, A_d_inv_cols, P_i_net_safe, P_node_inj, loss_ij, ci_ij)

    # 7. Final Output Assembly
    node_flow_without_loss = (P_ij * ci_ij).sum(axis=1)
    node_flow = node_flow_without_loss + surcharge

    # Flow Intensity handling (including zero-injection nodes)
    flow_intensity = node_flow / np.where(P_node_inj != 0, P_node_inj, np.inf)
    id_0_nodes = np.where(np.abs(P_ij.sum(axis=1)) <= 1e-8)[0]
    
    for idx in id_0_nodes:
        idx_pos = P_ij[idx, :] > 0
        if np.any(idx_pos):
            flow_intensity[idx] = (P_ij[idx, idx_pos] * ci_ij[idx, idx_pos]).sum() / P_ij[idx, idx_pos].sum()

    node_emission = -(node_flow - P_gen * carriers)
    
    # Eject Intensity
    eject_intensity = flow_intensity.copy()
    prosumer_mask = (P_gen != 0) & (P_load != 0)
    for i in np.where(prosumer_mask)[0]:
        if P_gen[i] >= P_load[i]:
            eject_intensity[i] = carriers[i]
        else:
            eject_intensity[i] = node_emission[i] / P_load[i]

    return node_flow, flow_intensity, node_emission, eject_intensity




