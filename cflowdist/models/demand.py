from demandlib import bdew
import pandas as pd
import numpy as np
from .. import network
from workalendar.europe import switzerland
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core import CarbonTracer
    from pandapower import pandapowerNet



def naive(df_p_mw_t: pd.DataFrame, snapshots: pd.DatetimeIndex, pp_grid: "pandapowerNet") -> pd.DataFrame:
    """
    Generate naive load profiles based on the rated power of each load in the pandapower grid. The load profile is generated using a simple hourly load factor that varies throughout the day. 
    The function iterates through each load in the pandapower grid and applies the naive load profile to generate the power demand for each snapshot. The resulting DataFrame contains the power demand for each load at each snapshot.

    Parameters
    ----------
    df_p_mw_t : pd.DataFrame
        A DataFrame to store the generated load profiles, indexed by snapshots and with columns corresponding to load indices in the pandapower grid.
    snapshots : pd.DatetimeIndex
        A DatetimeIndex representing the time snapshots for which the load profiles should be generated.
    pp_grid : pandapowerNet
        A pandapower network object containing the load information, including the rated power for each load.

    Returns
    -------
    pd.DataFrame
        A DataFrame containing the generated load profiles for each load at each snapshot, indexed by snapshots and with columns corresponding to load indices in the pandapower grid.

    See Also
    --------
    - [models.demand.p_est_naive](/reference/models.demand.p_est_naive.qmd) : 
        A helper function that generates a naive load profile for a single load based on its yearly average power and the hourly load factors defined.
    - [models.demand.landuse](/reference/models.demand.landuse.qmd) : 
        A function that generates load profiles based on land use data and standard load profiles for different sectors.
    """
    for idx, row in pp_grid.load.iterrows():
        df_p_mw_t.loc[:, idx] = p_est_naive(snapshots=snapshots, yearly_average_power=row['p_mw'])
    return df_p_mw_t.copy(deep=True)

def landuse(snapshots: pd.DatetimeIndex, pp_grid: "pandapowerNet", tracer: "CarbonTracer") -> pd.DataFrame:
    """
    Generate load profiles based on land use data and standard load profiles for different sectors. The function uses the BDEW standard load profiles for electricity demand, which are adjusted based on the annual electricity demand for each load in the pandapower grid. 
    The resulting DataFrame contains the power demand for each load node at each snapshot, indexed by snapshots and with columns corresponding to load indices in the pandapower grid.

    Parameters
    ----------
    snapshots : pd.DatetimeIndex
        A DatetimeIndex representing the time snapshots for which the load profiles should be generated.
    pp_grid : pandapowerNet
        A pandapower network object containing the load information, including the rated power for each load and the load type (e.g., residential, commercial, industrial).
    tracer : CarbonTracer
        A CarbonTracer object.
    
    Returns
    -------
    pd.DataFrame
        A DataFrame containing the generated load profiles for each load at each snapshot, indexed by snapshots and with columns corresponding to load indices in the pandapower grid.
    
    See Also
    --------
    - [models.demand.naive](/reference/models.demand.naive.qmd) : A function that generates naive load profiles for all loads in the pandapower grid using the `p_est_naive` helper function.
    """
    pp_grid.load['load_type'] = pp_grid.bus.load_type[pp_grid.load.bus].values
    local_snapshots = snapshots.tz_localize(None)
    df_p_mw_t = pd.DataFrame(index=local_snapshots, columns=pp_grid.load.index, data=np.zeros((len(snapshots), pp_grid.load.shape[0])))
    
    canton_located, _ = network.find_canton(tracer)
    cal = getattr(switzerland,canton_located , None)()
    elec_demands = [] 
    for year_selected in local_snapshots.year.unique():
        holidays = dict(cal.holidays(year_selected))
        ann_el_demand_per_sector = {
            "g0" :    8760,
            "g1" :   8760,
            "g2" :    8760,
            "g3" :    8760,
            "g6" :   8760,
            "h0" :    8760,
            "l0" :    8760,
        }
        year = year_selected
        # standard load profiles
        e_slp = bdew.ElecSlp(year, holidays=holidays)
        # multiply given annual demand with timeseries
        elec_demands.append(e_slp.get_profile(ann_el_demand_per_sector))
    elec_demands = pd.concat(elec_demands)
    elec_demands_hourly = elec_demands.resample('1h').mean()
    elec_demands_hourly_normalized = elec_demands_hourly/elec_demands_hourly.max()
    demand_factor = elec_demands_hourly_normalized.loc[local_snapshots]
    

    for idx, row in pp_grid.load.iterrows():
        df_p_mw_t.loc[:, idx] = row['p_mw']*demand_factor[row['load_type']]
    df_p_mw_t = df_p_mw_t.tz_localize(tracer.tz, ambiguous='infer')

    return df_p_mw_t.copy(deep=True)

def p_est_naive(snapshots: pd.DatetimeIndex, yearly_average_power: float) -> pd.Series:
    """
    A helper function that generates a naive load profile for a single load based on its yearly average power and the hourly load factors defined. 
    The function creates a load profile by multiplying the yearly average power with the corresponding hourly load factor for each snapshot.
    The resulting Series contains the estimated power demand for the load at each snapshot, indexed by snapshots.

    Parameters
    ----------
    snapshots : pd.DatetimeIndex
        A DatetimeIndex representing the time snapshots for which the load profile should be generated.
    yearly_average_power : float
        The yearly average power demand for the load, which is used to scale the hourly load factors to generate the load profile.

    Returns
    -------
    pd.Series
        A Series containing the estimated power demand for the load at each snapshot, indexed by snapshots.
    
    See Also
    --------
    - [models.demand.naive](/reference/models.demand.naive.qmd) : A function that generates naive load profiles for all loads in the pandapower grid using the `p_est_naive` helper function.
    """
    # naive method to generate loads
    hour =np.arange(24)
    load_factor = [0.3, 0.25, 0.22, 0.2, 0.2, 0.2, 0.25, 0.3, 0.4, 0.45, 0.5, 0.6, 0.6, 0.65, 0.55, 0.7, 0.8, 0.9, 1, 0.9, 0.8, 0.6, 0.5, 0.4]
    household_dict_hour = dict(zip(hour, load_factor))  

    load_p = []
    for sn in snapshots:
        load_p.append(household_dict_hour[sn.hour] * yearly_average_power)

    return pd.Series(data=load_p, index=snapshots)