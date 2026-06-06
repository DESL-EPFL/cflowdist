import os

import numpy as np
import json
import pickle
import requests
import shapely
import geopandas as gpd
import copy
import pandas as pd
import pandapower as pp
from pyproj import Transformer
from .models import generation, demand
import folium
import branca.colormap as cm
import branca
import folium.plugins
from folium.plugins import TimeSliderChoropleth
import pandapower.control as control
import pandapower.timeseries as timeseries
from pandapower.timeseries.data_sources.frame_data import DFData
from . import carbon, plot, grid, network
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

def load_json_file(json_path, logger=None, encoding=None):
    """
    Load a JSON file, possibly logging errors.

    Parameters
    ----------
    json_path : path_like
        Relative path to the JSON file.
    logger : logging.Logger (optional, default None)
        Logger to use.
    encoding : str (optional, default None)
        Encoding to use.  None means system preferred encoding.

    Returns
    -------
    contents : dict
        Contents of the JSON file.
    """
    try:
        with open(json_path, 'r', encoding=encoding) as json_file:
            contents = json.load(json_file)
    except OSError as e:
        if logger is not None:
            logger.error("Could not open {}: {}".format(json_path, e))
        raise
    except ValueError as e:
        if logger is not None:
            logger.error("Could not load {}: {}".format(json_path, e))
        raise

    return contents


def printv(str, verbose):
    if verbose:
        print(str)


@dataclass
class Location:
    """
    A class to represent a location with geocoding. The geocoding is done using the Swisstopo Geocoding API, which provides accurate geocoding results for Swiss addresses.

    Parameters
    ------
    address : str
        The address of the location to geocode.
    
    Attributes
    ------
    longitude : float
        The longitude of the geocoded location.
    latitude : float
        The latitude of the geocoded location.
    """
    address: str
    longitude: float = field(init=False)
    latitude: float = field(init=False)

    def __post_init__(self):

        url = "https://api3.geo.admin.ch/rest/services/ech/SearchServer"
        params = {
            "searchText": self.address,
            "type": "locations",
            "origins": "address",
            "sr": "4326"
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Swisstopo Geocoding API request failed: {e}")

        # Check if any results were found
        results = data.get("results", [])
        if not results:
            raise Exception(f"The address given ('{self.address}') cannot be recognized by swisstopo. Please adjust and try again.")
        
        location_attrs = results[0]["attrs"]
        self.longitude = location_attrs["lon"]
        self.latitude = location_attrs["lat"]


@dataclass
class CarbonTracer:
    """
    A class to trace carbon flows in the power grid.

    Parameters
    ----------
    address: str
        The address of the location to analyze.
    dir_config: str, optional
        Path to the configuration file, default "./config/default.json".

    Attributes
    ----------
    config: dict[str,dict]
        The loaded configuration from the JSON file.
    all_plant_df: gpd.GeoDataFrame
        A GeoDataFrame containing all the power plants.
    mv_hulls: dict[str, list]
        A dictionary containing the convex hulls of the MV grids.
    lv_hulls: dict[str, list]
        A dictionary containing the convex hulls of the LV grids.
    all_lu: gpd.GeoDataFrame
        A GeoDataFrame containing all the land use data.
    lu_46_category: pd.DataFrame
        A DataFrame mapping land use categories to 46 categories.
    pp_grid: pp.pandapowerNet
        The pandapower network representing the power grid.
    pf_calculator: grid.PowerFlowCalculator
        An instance of the PowerFlowCalculator class to perform power flow calculations.
    loc_selected: Location
        The geocoded location based on the provided address.
    node_ci_df: pd.DataFrame
        A DataFrame containing the carbon intensity at the node level.
    net_ci_df: pd.DataFrame
        A DataFrame containing the carbon intensity aggregated to the network level (weighted average).
    node_ce_df: pd.DataFrame
        A DataFrame containing the carbon emissions at the node level.
    net_ce_df: pd.DataFrame
        A DataFrame containing the carbon emissions aggregated to the network level.
    """
    address: str
    dir_config: str = "./config/default.json"
    config: dict[str,dict] = field(init=False)
    all_plant_df: gpd.GeoDataFrame = field(init=False)
    mv_hulls: dict[str, list] = field(init=False)
    lv_hulls: dict[str, list] = field(init=False)
    all_lu: gpd.GeoDataFrame = field(init=False)
    lu_46_category: pd.DataFrame = field(init=False)
    pp_grid: pp.pandapowerNet = field(init=False)
    pf_calculator: grid.PowerFlowCalculator = field(init=False)
    
    loc_selected: Location = field(init=False)


    node_ci_df: pd.DataFrame = field(init=False)
    net_ci_df: pd.DataFrame = field(init=False)
    node_ce_df: pd.DataFrame = field(init=False)
    net_ce_df: pd.DataFrame = field(init=False)
    enduse_EL_by_net: pd.DataFrame = field(init=False)
    weighted_net_ci_df: pd.DataFrame = field(init=False)
    local_PV_by_net: pd.DataFrame = field(init=False)


    def __post_init__(self):
        print("Geocoding...", end='', flush=True)

        self.loc_selected = Location(self.address)
        # loc = self.__geolocator.geocode(self.address)
        # if loc == None:
        #     raise Exception('The address given cannot be recognized, please adjust and try again.')
        # self.loc_selected = loc
        # loc_point = shapely.Point(loc.longitude, loc.latitude)
        print(f"Location coordinates: lon:{self.loc_selected.longitude}, lat:{self.loc_selected.latitude} !\n")


        # get infos related to power network
        print("Loading configuration... ", end='', flush=True)
        self.config = load_json_file(self.dir_config)
        print("Loaded!\n")
        path_dict = self.config['path']
        self.path_dict = path_dict


        _, self.canton_located = network.find_canton(self)

        print("Loading plants... ", end='', flush=True)
        self.all_plant_df = gpd.read_parquet(path_dict['plants'])
        print("Loaded!\n")

        print("Loading hulls... ", end='', flush=True)
        self.lv_2_mv = load_json_file(path_dict['lv_2_mv'])
        self.mv_hulls_gdf = gpd.read_file(path_dict['mv_hulls']) # convex hulls of the MV grids
        self.lv_hulls_gdf = gpd.read_file(path_dict['lv_hulls']) # convex hulls of the LV grids
        print("Loaded!\n")

        print("Loading landuse... ", end='', flush=True)
        self.all_lu = gpd.read_parquet(path_dict['lu'])
        lu_46_category = pd.read_csv(path_dict['lu_46_category'])
        lu_46_category.index = lu_46_category.lu_46_index.astype(str)
        lu_46_category.drop(columns='lu_46_index',inplace=True)
        self.lu_46_category = lu_46_category
        print("Loaded!\n")
        
        
        self.mv_plant_df = None
        self.tz = network.get_timezone_from_location(self.loc_selected)
        self.is_converged = False
        self.snapshots = None
        self.gen_p_mw_t = None
        self.sgen_p_mw_t = None
        self.load_p_mw_t = None
        
        self.pp_grid = self._construct_grids()

    def __str__(self) -> str:
        return f"CarbonTracer for address: {self.address}, located in canton: {self.canton_located}, timezone: {self.tz}."
    
    def __repr__(self) -> str:
        return self.__str__()
        
   
    def _construct_grids(self):
        """
        Constructs the pandapower networks.
        """


        print('Looking for the ids of the MV and LV grids...', end='', flush=True)
        mv_id, lv_id = network.find_id(self)
        print(f'Found MV grid id: {mv_id}!\n')
        print('Constructing pandapower network...', end='', flush=True)
        # If the mv_id.json is not found locally, try to load it from the remote repository
        if not os.path.exists(f'{self.path_dict["pp_grid_local"]}mv_{mv_id}.json'):
            print(f'Local file for MV grid {mv_id} not found, trying to download from remote repository...')
            # if the local directory for pp_grid does not exist, create it
            if not os.path.exists(self.path_dict["pp_grid_local"]):
                os.makedirs(self.path_dict["pp_grid_local"])
            try:
                # save to the local path for later use
                request_url = f'{self.path_dict["pp_grid_remote"]}mv_{mv_id}.json'
                request = requests.get(request_url)
                if request.status_code == 200:
                    with open(f'{self.path_dict["pp_grid_local"]}mv_{mv_id}.json', 'wb') as f:
                        f.write(request.content)
                print('Downloaded from remote repository!')
            except Exception as e:
                print(f'Failed to download from remote repository: {e}')
                raise Exception(f'MV grid data for mv_id {mv_id} not found locally or remotely, please check the mv_id and try again.')

        pp_grid = pp.from_json(f'{self.path_dict["pp_grid_local"]}mv_{mv_id}.json')
        assert type(pp_grid) == pp.pandapowerNet, 'The pandapower network is not correctly loaded.'
        


        if pp.__version__ > '2.xx':
            # pandapower 3.0+ moved bus_geodata to bus.geo, here we recover it


            pp_grid.bus_geodata = pp_grid.bus.geo.apply(lambda x: pd.Series(json.loads(x)['coordinates']))
            pp_grid.bus_geodata.columns = ['x', 'y']

            pp_grid.line_geodata = pp_grid.line.geo.apply(lambda x: json.loads(x)['coordinates']).to_frame()
            pp_grid.line_geodata.columns = ['coords']

        print('Constructed !')
        self.pp_grid = pp_grid
        print('Adding landuse data...', end='', flush=True)
        landuse, load_type = network.add_landuse(self.pp_grid.bus_geodata, all_lu=self.all_lu,
                                                      lu_46_category=self.lu_46_category)
        self.pp_grid.bus['landuse'] = landuse
        self.pp_grid.bus['load_type'] = load_type
        print('Done!\n')
               
        print('Adding generators...', end='', flush=True)
        with open(f'{self.path_dict["netid_ppid_dict"]}', 'r') as json_file:
            netid_ppid_dict = json.load(json_file)

        bus_max_power = (self.pp_grid.line.groupby('from_bus')['max_i_ka'].sum().add(self.pp_grid.line.groupby('to_bus')['max_i_ka'].sum(), fill_value=0))*self.pp_grid.bus.vn_kv*1000
        self.pp_grid.bus['bus_max_power'] = bus_max_power

        self.mv_plant_df = self.all_plant_df.to_crs(epsg=4326).loc[netid_ppid_dict[mv_id]]

       
        # Create a transformer from EPSG:2056 to EPSG:4326
        busgeo_transformer = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
        # Convert each point to EPSG:4326
        (lon,lat) = busgeo_transformer.transform(self.pp_grid.bus_geodata.x, self.pp_grid.bus_geodata.y)
        self.pp_grid.bus['x'] = lon
        self.pp_grid.bus['y'] = lat

        # Handle over-capacity buses
        local_plant_df = network.ckdnearest(self.mv_plant_df, self.pp_grid.bus)
        overcap_gens = local_plant_df[local_plant_df.TotalPower > local_plant_df.bus_max_power]

        for xtf_id, row in overcap_gens.iterrows():
            buses = self.pp_grid.bus[self.pp_grid.bus['bus_max_power'] > row['TotalPower']]
            local_plant_df.loc[xtf_id] = network.ckdnearest(overcap_gens.loc[[xtf_id]],buses).iloc[0]
        self.mv_plant_df = local_plant_df
        
        for xtf_id, row in self.mv_plant_df.iterrows():
            if row.bus_id not in self.pp_grid.gen.bus.unique():
                # Assume plants >5MW as PV nodes, else PQ nodes
                if row['TotalPower'] > 5000:
                    pp.create_gen(net=self.pp_grid, bus=row.bus_id, p_mw=row['TotalPower']/1000, name = xtf_id, type=row['SubCategory'])
                else:
                    pp.create_sgen(net=self.pp_grid, bus=row.bus_id, p_mw=row['TotalPower']/1000, q_mvar=0,name = xtf_id, type=row['SubCategory'])
        print("Done!")
        return self.pp_grid

    def set_snapshots(self, t_start:str, t_end:str, freq = '1h') -> pd.DatetimeIndex:
        """
        Set snapshots for power flow and carbon allocation after.

        Parameters
        ----------
        t_start : str
            Starting time.
        t_end : str
            Ending time.
        freq : str, default '1h'
            Frequency, default hourly.
        Returns
        ----------
        pd.DatetimeIndex

        Example
        ------
        ```python
        t_start = '2023-06-08 12:00:00'
        t_end = '2023-06-08 14:00:00'
        snapshots = tracer.set_snapshots(t_start=t_start, t_end=t_end)
        ```
        """
        if self.tz == None:
            raise Exception('Timezone info is required, please construct grid first.')
        snapshots = pd.date_range(start= t_start, end=t_end, freq= freq, tz=self.tz)
        # TODO: limit: ci_ch
        if (snapshots.year != 2023).sum():
            raise Exception('ValueError: currently only support year 2023, to support other years, please make sure that the intensities of the transmission-level network are available in `test/data/carbon/`.')
        self.snapshots = snapshots
        if len((snapshots-snapshots.tz_localize(None).tz_localize('UTC')).unique()) >1:
            print("The selected time period includes day light saving time changes, which has been considered.")

        # remove future installed plants according to the generation dataset
        grid.remove_future_plants(self, snapshots[0])

        return snapshots

    def power_flow(self) -> None:
        """
        Run power flow (by pandapower time series simulation).

        See Also
        --------
        - [grid.PowerFlowCalculator](/reference/grid.PowerFlowCalculator.qmd)
        """
        self.pf_calculator = grid.PowerFlowCalculator(tracer=self)
        self.pf_calculator.run_power_flow()

    def allocate_carbon(self, return_scale: Literal['node', 'lv_net'] = 'node', loss_allocation:bool = False, self_consumption:bool = True, use_numba:bool = False):
        """
        Allocate carbon emissions to the nodes using the flow tracing algorithms developed (LL, LL-P and LA methods). 

        Parameters
        ----------
        return_scale: Literal['node', 'lv_net'], default 'node'
            The scale to return the carbon intensity results, either at 'node' level or aggregated to 'lv_net' level.
        loss_allocation: bool, default False
            Whether to allocate losses to the nodes. If True, the carbon intensity will be allocated considering the losses, i.e. the LA method. If False, the carbon intensity will be allocated without considering losses.
        self_consumption: bool, default True
            Whether to prioritize self-consumption in the flow tracing algorithm. If True, the algorithm will prioritize self-consumption when allocating carbon intensity (LL-P method). If False, the algorithm will not prioritize self-consumption (LL method).
        use_numba: bool, default False
            Whether to use numba JIT compiler for faster computation. If True, numba will be used to speed up the LA method, only valid when `loss_allocation` is True. 
            Note that for large networks with more than 500 nodes, it is recommended to set `use_numba` to True for faster computation, as the LA method can be computationally intensive for large networks.
        
        Returns
        -------
        pd.DataFrame
            A DataFrame containing the allocated carbon intensity, either at node level or aggregated to lv_net level, depending on the `return_scale` parameter.
        """
        if hasattr(self, 'pf_calculator'):
            if not self.pf_calculator.is_converged:
                raise Exception('Please make sure  the power flow converges before allocating emissions.')
        else:
            raise Exception('Please run power flow before allocating emissions.')
        
        snapshots = self.snapshots
        assert snapshots is not None, 'Please set snapshots before allocating emissions.'
        ci_df = carbon.carrierinit(self)
        self.ci_df = ci_df

        pp_grid = self.pp_grid

        n_node = pp_grid.bus.shape[0]
        node_ci_df = pd.DataFrame(index=snapshots, columns=pp_grid.bus.index, data=np.zeros((len(snapshots), n_node)))
        node_ce_df = pd.DataFrame(index=snapshots, columns=pp_grid.bus.index, data=np.zeros((len(snapshots), n_node)))

        # pf_results = carbon.read_pf_results(tz=self.tz)
        # self.pf_results = pf_results

        # pf_results = self.pf_calculator.pf_results

        for step in snapshots:
            print(step)
            if loss_allocation:
                if n_node > 500 and not use_numba:
                    print('Warning: large networks may cost very long time, network with 1500 nodes takes about 1 minute for computing 1 snapshot. Consider using numba JIT compiler by setting use_numba = True for faster computation.')
                step_flow_data = carbon.organize_step_flow_data(pf_calculator=self.pf_calculator, ci_df=ci_df, step=step)
                ci, ce = carbon.carbon_tracing_ap_with_losses(step_flow_data, use_numba=use_numba)
            else:
                step_flow_data = carbon.organize_step_flow_data(pf_calculator=self.pf_calculator, ci_df=ci_df, step=step)
                ci,ce = carbon.carbon_tracing_ap(step_flow_data, self_consumption=self_consumption)
            node_ci_df.loc[step] = ci
            node_ce_df.loc[step] = ce
        node_ci_df.columns = pp_grid.bus.name
        node_ce_df.columns = pp_grid.bus.name
        
        co2_by_net = []
        for t, row in node_ci_df.iterrows():
            co2_intensity_df = pd.DataFrame(row)
            co2_intensity_df['net_id'] = co2_intensity_df.index
            co2_intensity_df[['net_id', 'node']] = co2_intensity_df['net_id'].str.split('_node_', expand=True)
            co2_intensity_df['net_id'] = co2_intensity_df['net_id'].str.split('bus_', expand=True)[1]
            co2_by_net.append(co2_intensity_df.groupby('net_id')[t].mean())
        self._raw_net_ci_df = pd.DataFrame(co2_by_net)
        self.node_ci_df = node_ci_df
        self.node_ce_df = node_ce_df
        
        carbon.post_process_carbon(self)

        if return_scale == 'node':
            return self.node_ci_df
        elif return_scale == 'lv_net':
            assert hasattr(self, 'net_ci_df'), 'Network level carbon intensity dataframe not found, please run carbon allocation first.'
            return self.net_ci_df
        else:
            raise Exception("Please choose between 'node' and 'lv_net'.")

    def network_plot(self, show_tools: bool = True):
        """
        Plot network topology using folium, including HV, MV and LV buses, generation plants, as well as MV and LV lines.

        Parameters
        ------
        show_tools: bool, default True
            A boolean flag indicating whether to show the tools in the map. If True, a fullscreen button and a geocoder inputbox will be added to the map. 

        Returns
        ------
        folium.Map
            A pretty map visualization of the network `pp_grid`.
        
        Example
        ------
        ```python
        tracer.network_plot()
        ```
        """
        return plot.network_plot(self, show_tools=show_tools)

    def network_carbon_plot(self, snapshot: pd.Timestamp, show_colormap: bool = True, show_tools: bool = False):
        """
        Plot the calculated node-level carbon intensity using folium.

        Parameters
        ------
        snapshot: pd.Timestamp
            A selected timestamp to plot.
        show_colormap: bool, default True
            A boolean flag indicating whether to show a colormap in the map. If True, a colormap will be added to the map. 
        show_tools: bool, default False
            A boolean flag indicating whether to show the tools in the map. If True, a fullscreen button and a geocoder inputbox will be added to the map. 

        Returns
        ------
        folium.Map
            A pretty map visualization of the carbon allocation results.
        
        Example
        ------
        ```python
        tracer.network_carbon_plot(snapshot = tracer.snapshots[0])
        ```
        """
        return plot.network_carbon_plot(self, snapshot=snapshot, show_colormap=show_colormap, show_tools=show_tools)

    def network_dual_plot(self, snapshot_night: pd.Timestamp, snapshot_day: pd.Timestamp, show_colormap = False):
        """
        Plot the calculated node-level carbon intensity using folium dual map, comparing two snapshots horizontally, one with light style tile and one with dark style tile.

        Parameters
        ------
        snapshot_night: pd.Timestamp
            A selected night timestamp to plot.
        snapshot_day: pd.Timestamp
            A selected day timestamp to plot.
        show_colormap: bool, default True
            A boolean flag indicating whether to show a colormap in the map. If True, a colormap will be added to the map. 

        Returns
        ------
        folium.plugins.DualMap
            A pretty dual map visualization of the carbon allocation results.
        
        Example
        ------
        ```python
        tracer.network_dual_plot(snapshot_day = tracer.snapshots[12], snapshot_night= tracer.snapshots[0])
        ```
        """
        return plot.network_dual_plot(self, snapshot_night=snapshot_night, snapshot_day=snapshot_day, show_colormap=show_colormap)
    
    def lv_grids_time_plot(self, tile_name: str = 'white', show_tools:bool=False):
        """
        Plot the calculated carbon intensity aggegated to a LV-net level using folium TimeSliderChoropleth, with a time slider.

        Parameters
        ------
        tile_name: str, default 'white'
            A selected tile name for the basemap.
        show_tools: bool, default False
            A boolean flag indicating whether to show the tools in the map. If True, a fullscreen button and a geocoder inputbox will be added to the map. 

        Returns
        ------
        folium.Map
            A pretty map visualization of the carbon allocation results with a time slider.
        
        Example
        ------
        ```python
        tracer.lv_grids_time_plot()
        ```
        """
        return plot.lv_grids_time_plot(self, tile_name=tile_name, show_tools=show_tools)

    ## IO

    def save_pickle(self, filename:str) -> None:
        """
        Save a CarbonTracer object to a pickle file.

        Parameters
        ------
        filename : str
            Path to write the file.
        """
        self.all_lu = None
        self.all_plant_df = None

        filehandler = open(filename, 'wb') 
        pickle.dump(self, filehandler)

def read_pickle(filename: str, dir_config: str = "./config/default.json") -> CarbonTracer:
    """
    Read a CarbonTracer object from a pickle file.

    Parameters
    ----------
    filename : str
        Path to the pickle file.
    dir_config : str 
        Path to the configuration file, default "./config/default.json".

    Returns
    ----------
    CarbonTracer
        The loaded CarbonTracer object.

    Example
    ----------
    ```python
    tracer = read_pickle('tracer.pkl', dir_config="./config/default.json")
    ```
    """
    file = open(filename, 'rb')    
    tracer = pickle.load(file)
    print("Loading configuration... ", end='', flush=True)
    tracer.config = load_json_file(dir_config)
    print("Loaded!\n")
    path_dict = tracer.config['path']
    tracer.path_dict = path_dict

    print("Loading plants... ", end='', flush=True)
    tracer.all_plant_df = gpd.read_parquet(path_dict['plants'])
    print("Loaded!\n")

    print("Loading landuse... ", end='', flush=True)
    tracer.all_lu = gpd.read_parquet(path_dict['lu'])
    lu_46_category = pd.read_csv(path_dict['lu_46_category'])
    lu_46_category.index = lu_46_category.lu_46_index.astype(str)
    lu_46_category.drop(columns='lu_46_index',inplace=True)
    tracer.lu_46_category = lu_46_category
    print("Loaded!\n")

    return tracer