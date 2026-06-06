import pandas as pd
import numpy as np
import pvlib
from .. import roof
from datetime import timedelta
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..core import CarbonTracer, Location
    from ..grid import PowerFlowCalculator



pd.options.mode.chained_assignment = None

def primitive(df_p_mw_t: pd.DataFrame, df_gen: pd.DataFrame, snapshots: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Apply the primitive method to generation generator profiles. 
    The function iterates through each generator in the provided DataFrame and estimates the power output for photovoltaic (PV) generators using the `p_est_primitive` helper function, which is based on Global Horizontal Irradiance (GHI) data.
    For non-PV generators, the function assigns the rated power as the power output for all snapshots.
    The resulting DataFrame contains the estimated power output for each generator at each snapshot, indexed by snapshots and with columns corresponding to generator indices.

    Parameters
    ----------
    df_p_mw_t : pd.DataFrame
        A DataFrame to store the generated power profiles, indexed by snapshots and with columns corresponding to generator indices.
    df_gen : pd.DataFrame
        A DataFrame containing generator information (an attribute of the pandapower.pandapowerNet, `pp_grid.gen` or `pp_grid.sgen`), including the type of generator (e.g., 'Photovoltaic') and the rated power ('p_mw').
    snapshots : pd.DatetimeIndex
        A DatetimeIndex representing the time snapshots for which the generation profiles should be generated.
    
    Returns
    -------
    pd.DataFrame
        A DataFrame containing the estimated power output for each generator at each snapshot, indexed by snapshots and with columns corresponding to generator indices.
    
    See Also
    --------
    - [models.generation.p_est_primitive](/reference/models.generation.p_est_primitive.qmd) : A helper function that estimates photovoltaic (PV) power output using a primitive method based on Global Horizontal Irradiance (GHI) data.
    """
    for idx, row in df_gen.iterrows():
        if row['type'] == 'Photovoltaic':
            df_p_mw_t.loc[:, idx] = p_est_primitive(
                snapshots=snapshots,
                rated_power=row['p_mw'],
            )
        else:
            df_p_mw_t.loc[:, idx] = row['p_mw']

    return df_p_mw_t.copy(deep=True)

def upgrade_roof(df_p_mw_t: pd.DataFrame, df_gen: pd.DataFrame, snapshots: pd.DatetimeIndex, tracer: "CarbonTracer") -> pd.DataFrame:
    """
    Apply the upgrade_roof method to compute generation patterns.
    The function estimates the power output for photovoltaic (PV) generators using the `p_est_upgrade_roof` helper function, which takes into account roof inclination, orientation, and local weather conditions to estimate the power output of the PV system.
    For non-PV generators, the function assigns the rated power as the power output for all snapshots.
    The resulting DataFrame contains the estimated power output for each generator at each snapshot, indexed by snapshots and with columns corresponding to generator indices.

    Parameters
    ----------
    df_p_mw_t : pd.DataFrame
        A DataFrame to store the generated power profiles, indexed by snapshots and with columns corresponding to generator indices.
    df_gen : pd.DataFrame
        A DataFrame containing generator information (an attribute of the pandapower.pandapowerNet, `pp_grid.gen` or `pp_grid.sgen`), including the type of generator (e.g., 'Photovoltaic') and the rated power ('p_mw').
    snapshots : pd.DatetimeIndex
        A DatetimeIndex representing the time snapshots for which the generation profiles should be generated.
    tracer : CarbonTracer
        A CarbonTracer object that contains location information and other relevant data for estimating PV power output.
    
    Returns
    -------
    pd.DataFrame
        A DataFrame containing the estimated power output for each generator at each snapshot, indexed by snapshots and with columns corresponding to generator indices.
    
    See Also
    ------
    - [models.generation.p_est_upgrade_roof](/reference/models.generation.p_est_upgrade_roof.qmd) : A helper function that estimates PV power output by taking into account roof inclination, orientation, and local weather conditions using the pvlib library.
    """

    loc_selected = tracer.loc_selected
    tz = tracer.tz
    mv_plant_df = tracer.mv_plant_df

    date_start = (snapshots[0] - timedelta(days=1)).strftime('%Y-%m-%d')
    date_end = (snapshots[-1] + timedelta(days=1)).strftime('%Y-%m-%d')
    openmeteo_df = roof.get_open_meteo(location=loc_selected, date_start=date_start, date_end=date_end)
    openmeteo_df = openmeteo_df.tz_convert(tz).loc[snapshots]
    
    for idx, row in df_gen.iterrows():
        if row['type'] == 'Photovoltaic':
            df_p_mw_t.loc[:, idx] = p_est_upgrade_roof(openmeteo_df, loc_selected, roof_selected=mv_plant_df.loc[row['name']], tz = tz) / 1000 # from kW to MW
        else:
            df_p_mw_t.loc[:, idx] = row['p_mw']
    return df_p_mw_t.copy(deep=True)


def p_est_primitive(snapshots: pd.DatetimeIndex, rated_power: float, datafile: str ='../data/GHI/GHI_Swiss_Solcast.csv') -> pd.Series:
    """
    A helper function that estimates photovoltaic (PV) power output using a primitive method based on Global Horizontal Irradiance (GHI) data.
    The function reads GHI data from a CSV file, filters it for the specified snapshots, and calculates the power output as a fraction of the rated power based on the GHI values.
    The resulting Series contains the estimated power output for each snapshot.
    
    Parameters
    ----------
    snapshots : pd.DatetimeIndex
        A DatetimeIndex representing the time snapshots for which the load profiles should be generated.
    rated_power : float
        The rated power of the PV system, which is used to scale the estimated power output.
    datafile : str, optional
        The path to the CSV file containing the GHI data, by default '../data/GHI/GHI_Swiss_Solcast.csv'.

    Returns
    -------
    pd.Series
        A Series containing the estimated power output for each snapshot, indexed by snapshots.
    
    See Also
    --------
    - [models.generation.primitive](/reference/models.generation.primitive.qmd) 
    - [models.generation.upgrade_roof](/reference/models.generation.upgrade_roof.qmd)
    """
    ghidata = pd.read_csv(datafile)
    ghidata.index = pd.to_datetime(ghidata['period_end'], format='%Y-%m-%dT%H:%M:%SZ')
    ghidata.drop(columns=['period_end'], inplace=True)

    pvprod = ghidata.loc[snapshots[0]:snapshots[-1]]
    pvprod.loc[:, 'power_pu'] = np.array(pvprod.loc[:, 'ghi']/1000)*rated_power
    return pvprod['power_pu']

def p_est_upgrade_roof(openmeteo_df: pd.DataFrame, loc_selected: "Location", roof_selected: pd.Series, tz: str) -> pd.Series:
    """
    A helper function that estimates photovoltaic (PV) power output by taking into account roof inclination, orientation, and local weather conditions (GHI, DNI, DHI, temperature, and wind speed) using the pvlib library.
    The function calculates the solar position, plane of array irradiance, cell temperature, and finally the AC power output of the PV system based on the provided weather data and roof characteristics.
    The resulting Series contains the estimated power output for each snapshot, indexed by snapshots.

    Parameters
    ----------
    openmeteo_df : pd.DataFrame
        A DataFrame containing local weather data (GHI, DNI, DHI, temperature, and wind speed) indexed by snapshots, generated by `roof.get_open_meteo` function.
    loc_selected : "Location"
        The location for which to estimate PV power output.
    roof_selected : pd.Series
        A Series containing the roof characteristics for the PV system.
    tz : str
        The timezone of the location, used for time localization of the resulting Series.
    
    Returns
    -------
    pd.Series
        A Series containing the estimated power output for each snapshot, indexed by snapshots.
    
    See Also
    --------
    - [models.generation.primitive](/reference/models.generation.primitive.qmd)
    - [models.generation.upgrade_roof](/reference/models.generation.upgrade_roof.qmd)
    - [roof.get_open_meteo](/reference/roof.get_open_meteo.qmd) : A function that retrieves local weather data (GHI, DNI, DHI, temperature, and wind speed) for a given location and date range using the Open-Meteo API.
    """

    tilt = roof_selected.Roof_Inclination
    azimuth = roof_selected.Roof_Orientation + 180 # + 180 degree due to the definition of admin roof orientation
    capacity_kWp = roof_selected.TotalPower
    module_eff = 0.20 # defined
    derate_factor = 0.86 # defined

    loc_pv = pvlib.location.Location(loc_selected.latitude, loc_selected.longitude,tz=tz)
    time_range = openmeteo_df.index
    solar_position = loc_pv.get_solarposition(time_range)
    poa_irra = pvlib.irradiance.get_total_irradiance(surface_tilt=tilt,
                                                 surface_azimuth = azimuth,
                                                 dni= openmeteo_df.DNI.values,
                                                 ghi=openmeteo_df.GHI.values,
                                                 dhi=openmeteo_df.DHI.values,
                                                 solar_zenith = solar_position['zenith'],
                                                 solar_azimuth = solar_position['azimuth'])
    temp_cell = pvlib.temperature.pvsyst_cell(poa_global=poa_irra['poa_global'],
                                              u_c = 20.0,
                                              module_efficiency  = module_eff,
                                          temp_air = openmeteo_df.T_2m.values,
                                          wind_speed = openmeteo_df.W_10m.values)
    pvwatts_ac = pvlib.pvsystem.pvwatts_dc(effective_irradiance=poa_irra['poa_global'],temp_cell=temp_cell, pdc0=capacity_kWp, gamma_pdc=-0.004)
    pv_power = pvwatts_ac*derate_factor




    return pv_power