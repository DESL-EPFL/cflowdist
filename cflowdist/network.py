import requests
from scipy.spatial import cKDTree
import numpy as np
import geopandas as gpd
from timezonefinder import TimezoneFinder
from shapely.geometry import Point
import pandas as pd
import fiona
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .carbon import CarbonTracer
    from .core import Location

def ckdnearest(gdA: gpd.GeoDataFrame , gdB: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Finds the nearest node (bus) to which we can associate the power plant concerned,
    exploiting the geographical coordinates of the power plants and the network nodes.
    
    Parameters
    ------
    gdA: gpd.GeoDataFrame
        GeoDataFrame of power plants, must contain a 'geometry' column with Point geometries.
    gdB: gpd.GeoDataFrame
        GeoDataFrame of network nodes, must contain 'x' and 'y' columns with the coordinates of the nodes.
    
    Returns
    ------
    gpd.GeoDataFrame
        A modified version of gdA that includes three new columns:

        - `'bus_name'`: The name of the nearest node (bus) from gdB to which each power plant in gdA is assigned.
        - `'bus_id'`: The index of the nearest node (bus) from gdB to which each power plant in gdA is assigned.
        - `'bus_max_power'`: The maximum power of the nearest node (bus) from gdB to which each power plant in gdA is assigned.
    """
    if gdA.empty:
        return gdA
    
    #assert gdA.geometry.crs == gdB.geometry.crs, 'CRS must be the same.'
    
    nA = np.array(list(gdA.geometry.apply(lambda x: (x.x, x.y))))
    nB = gdB[['x','y']].values
    btree = cKDTree(nB)
    dist, idx = btree.query(nA, k=1)

    gdA.loc[:, ('bus_name')] = gdB.iloc[idx]['name'].values#name#gdB['name'][idx].values 
    gdA.loc[:, ('bus_id')] = idx
    gdA.loc[:, ('bus_max_power')] = gdB.iloc[idx]['bus_max_power'].values# gdB['bus_max_power'][idx].values

    return gdA

# def ckdnearest_one_to_one(gdA, gdB):
#     ''' 
#     Matches each power plant to the nearest unassigned node (one-to-one matching) based on geographical coordinates. 
#     Modifies gdA to include a 'bus_name' column that denotes the node to which each generator is uniquely assigned.
#     '''
#     if gdA.empty:
#         return gdA

#     # Extract coordinates from both GeoDataFrames
#     nA = np.array(list(gdA.geometry.apply(lambda x: (x.x, x.y))))
#     nB = gdB[['x','y']].values

#     # Build KD-tree for fast nearest-neighbor search
#     btree = cKDTree(nB)
#     dist, idx = btree.query(nA, k=1)

#     # Track assigned nodes to ensure one-to-one matching
#     assigned_nodes = set()

#     # Iterate through each generator in gdA and assign the nearest available node
#     bus_id_list = []
#     for i, generator_idx in enumerate(idx):
#         nearest_node = gdB.index[generator_idx]
        
#         # Find next available node if the nearest one is already assigned
#         if nearest_node in assigned_nodes:
#             # Query for multiple nearest nodes (k > 1) and find an unassigned node
#             dist_i, idx_i = btree.query(nA[i], k=len(nB))
#             for neighbor_idx in idx_i:
#                 nearest_node = gdB.index[neighbor_idx]
#                 if nearest_node not in assigned_nodes:
#                     assigned_nodes.add(nearest_node)
#                     bus_id_list.append(nearest_node)
#                     break
#         else:
#             assigned_nodes.add(nearest_node)
#             bus_id_list.append(nearest_node)
    
#     # Add the 'bus_name' column to gdA with unique nearest nodes
#     gdA['bus_id'] = bus_id_list
#     bus_name_dict = dict(zip(gdB.index.to_list(), range(len(gdB))))
#     gdA['bus_name'] = gdB.name[bus_id_list].values#[bus_id_dict.get(bus_name) for bus_name in bus_name_list]
    
#     return gdA


def read_gpkg(file: str) -> dict:
    """
    Read a GeoPackage file and return a dictionary of GeoDataFrames.

    Parameters
    ------
    file: str
        The path to the GeoPackage file.

    Returns
    ------
    dict
        A dictionary where the keys are the layer names and the values are the corresponding GeoDataFrames
    
    """
    layers = fiona.listlayers(file)
    data = dict()

    for layer in layers:
        data[layer] = gpd.read_file(file, layer=layer)
    
    return data

def get_timezone_from_location(location: "Location") -> str:
    """
    Get the timezone of a given Location object.
    
    Parameters
    ------    
    location: Location
        The location object containing latitude and longitude.
        
    Returns
    ------
    str
        The timezone name (e.g., 'America/New_York').
    """
    if not location:
        raise ValueError("Location is required.")
    
    tf = TimezoneFinder()
    lat, lon = location.latitude, location.longitude
    timezone_name = tf.timezone_at(lat=lat, lng=lon)
    
    if not timezone_name:
        raise ValueError("Timezone could not be determined for the given location.")
    
    return timezone_name



def find_best_polygon(gdf: gpd.GeoDataFrame, pt: Point) -> str:
    """
    Find the polygon in gdf that best matches the point.

    Rule:

      - If point is contained in one or more polygons -> choose polygon with closest centroid.
      - Else -> choose polygon with closest centroid.
    
    Parameters
    ------
    gdf: gpd.GeoDataFrame
        GeoDataFrame containing the polygons to be searched.
    pt: Point
        Shapely Point object representing the location to be matched.
    
    Returns
    ------
    str
        The identifier of the best matching polygon (e.g., canton name or code).
    """
    # candidate polygons that contain the point

    containing = gdf[gdf.contains(pt)]
    
    if not containing.empty:
        # pick containing polygon with centroid closest to the point
        containing["centroid_dist"] = containing.to_crs(3785).centroid.distance(pt)
        best = containing.loc[containing["centroid_dist"].idxmin()]
    else:
        # pick nearest polygon centroid overall
        # gdf["centroid_dist"] = gdf.centroid.distance(pt)
        # best = gdf.loc[gdf["centroid_dist"].idxmin()]
        original_crs = gdf.crs
        gdf_projected = gdf.to_crs(epsg=2056)
        pt_projected = gpd.GeoSeries([pt], crs=original_crs).to_crs(epsg=2056).iloc[0]
        gdf_projected["centroid_dist"] = gdf_projected.centroid.distance(pt_projected)
        best_idx = gdf_projected["centroid_dist"].idxmin()
        best = gdf.loc[best_idx]
    
    return best.id


def find_id(tracer: "CarbonTracer") -> tuple[str, str]:
    """
    Find the identifiers of the best matching MV and LV network ID for the location of the tracer, based on the LV and MV hulls in the tracer's data.
    The function uses the `find_best_polygon` helper function to find the best matching polygon for the tracer's location in both the LV and MV hulls, and returns the corresponding identifiers for the MV and LV networks.

    Parameters
    ------
    tracer: "CarbonTracer"
        An instance of the CarbonTracer class, which contains the location of the tracer and the LV and MV hulls as GeoDataFrames.

    Returns
    ------
    tuple[str, str]
        A tuple containing the identifiers of the best matching MV and LV network ID for the tracer's location, in the format (MV_ID, LV_ID).

    See Also
    ------
    - [find_best_polygon](/reference/network.find_best_polygon.qmd)
    """

    lv_id = find_best_polygon(
        gdf = tracer.lv_hulls_gdf,
        pt = Point(tracer.loc_selected.longitude, tracer.loc_selected.latitude)
        )
    
    
    mv_id = tracer.lv_2_mv.get(lv_id)

    return mv_id, lv_id



def add_landuse(bus_geodata: gpd.GeoDataFrame, all_lu: gpd.GeoDataFrame, lu_46_category: pd.DataFrame):
    """
    Add land use category to the bus geodata based on the nearest land use polygon.

    Parameters
    ----------
    bus_geodata: gpd.GeoDataFrame
        GeoDataFrame containing the bus geodata, must include 'x' and 'y' columns for the coordinates of the buses.
    all_lu: gpd.GeoDataFrame
        GeoDataFrame containing the land use polygons, must include a 'geometry' column with Polygon
        geometries and a 'lu_46' column with the land use category codes.
    lu_46_category: pd.DataFrame
        DataFrame containing the mapping of land use category codes to their names and BDEW load types defined.
    
    Returns
    ------
    tuple[np.ndarray, np.ndarray]
        A tuple containing two numpy arrays:
        
        - The first array contains the land use category names corresponding to each bus, based on the nearest land use polygon.
        - The second array contains the BDEW load types corresponding to each bus, based on the nearest land use polygon and the mapping provided in `lu_46_category`.
    """
    bus_geodata = bus_geodata.copy(deep=True)
    def find_nearest(bus_gdf, lu_gdf):
        nA = np.array(list(bus_gdf.geometry.apply(lambda x: (x.x, x.y))))
        nB = np.array(list(lu_gdf.geometry.apply(lambda x: (x.x, x.y))))
        btree = cKDTree(nB)
        dist, idx = btree.query(nA, k=1)

        bus_gdf.loc[:, ('nearest_index')] = lu_gdf.index[idx] #gdB.iloc[idx].name
        return bus_gdf

    bus_geodata['geometry'] = bus_geodata.apply(lambda row: Point(row["x"], row["y"]), axis=1)
    bus_gdf  = gpd.GeoDataFrame(bus_geodata, geometry="geometry", crs="EPSG:2056")
    lu_near = all_lu[(all_lu.geometry.x <= bus_gdf.x.max()+100) & (all_lu.geometry.x >= bus_gdf.x.min()-100) & (all_lu.geometry.y <= bus_gdf.y.max()+100) & (all_lu.geometry.y >= bus_gdf.y.min()-100)]
    bus_gdf = find_nearest(bus_gdf, lu_near)
    lu_match = lu_near.loc[list(bus_gdf.nearest_index)]
    bus_gdf['lu_46'] = lu_match['lu_46'].values
    return bus_gdf['lu_46'].apply(lambda x: lu_46_category.lu_46_name.loc[x]).values, bus_gdf['lu_46'].apply(lambda x: lu_46_category.bdew_load_type.loc[x]).values

# def find_canton(tracer: "CarbonTracer") -> tuple[str, str]:
#     """
#     Find the canton name and code for the location of the tracer, based on the Swiss canton boundaries in the tracer's data.
#     If the location of the tracer falls outside the boundaries of all Swiss cantons, a ValueError is raised.
     
#     Parameters
#     ------
#     tracer: "CarbonTracer"
#         An instance of the CarbonTracer class, which contains the location of the tracer.
    
#     Returns
#     ------
#     tuple[str, str]
#         A tuple containing the name and code of the canton for the tracer's location, in the format (canton_name, canton_code), e.g. `('Vaud', 'VD')`.
#     """
#     loc_selected = tracer.loc_selected
#     loc_point = Point(loc_selected.longitude, loc_selected.latitude)
#     canton = gpd.read_file(f'{tracer.path_dict['swiss_boundaries']}',layer = 'tlm_kantonsgebiet')[['name','geometry']]
#     canton['name_calendar'] = ['Graubunden', 'Bern','Valais', 'Vaud', 'Ticino', 'StGallen', 'Zurich',
#                             'Fribourg', 'Luzern', 'Aargau', 'Uri', 'Thurgau', 'Schwyz', 'Jura', 'Neuchatel', 'Solothurn', 
#                             'Glarus', 'BaselLandschaft', 'Obwalden', 'Nidwalden', 'Geneva', 'Schaffhausen', 'AppenzellAusserrhoden', 
#                             'Zug', 'AppenzellInnerrhoden', 'BaselStadt']
#     canton['name_code'] = ['GR', 'BE', 'VS', 'VD', 'TI', 'SG', 'ZH', 'FR', 'LU', 'AG', 'UR', 'TG', 'SZ', 'JU', 'NE', 'SO', 'GL', 'BL', 'OW', 'NW', 'GE', 'SH', 'AR', 'ZG', 'AI', 'BS']

#     is_in_canton = canton.to_crs(epsg=4326).geometry.contains(loc_point)

#     if not is_in_canton.any():
#         raise ValueError("The location of the tracer does not fall within any canton in the Swiss boundaries dataset.")


#     canton_name_for_calendar = canton.name_calendar[canton.to_crs(epsg=4326).geometry.contains(loc_point)].iloc[0]
#     canton_code = dict(zip(canton['name_calendar'], canton['name_code']))[canton_name_for_calendar]
#     return canton_name_for_calendar, canton_code

def find_canton(tracer: "CarbonTracer") -> tuple[str, str]:
    """
    Find the canton name and code for the location of the tracer using the swisstopo Web API.
    Raises a ValueError if the location falls outside Switzerland.
    
    Returns
    ------
    tuple[str, str]
        (canton_name_for_calendar, canton_code), e.g. `('Vaud', 'VD')`, `Zurich', 'ZH')`
    """
    loc_selected = tracer.loc_selected
    
    # Swisstopo API endpoint for identifying features by coordinates
    url = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
    
    # Set up the parameters required by swisstopo
    params = {
        "geometryType": "esriGeometryPoint",
        "geometry": f"{loc_selected.longitude},{loc_selected.latitude}",
        "imageDisplay": "0,0,0",
        "mapExtent": "0,0,0,0",
        "tolerance": 0,
        "layers": "all:ch.swisstopo.swissboundaries3d-kanton-flaeche.fill", # The  canton boundaries layer
        "sr": "4326"
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Swisstopo API request failed: {e}")

    # If the results list is empty, the point is outside Swiss borders
    if not data.get("results"):
        raise ValueError("The location of the tracer does not fall within any canton in the Swiss boundaries dataset.")
    
    # Extract properties from the first match
    properties = data["results"][0]["attributes"]
    canton_code = properties["ak"]

    name_for_calendar = ['Graubunden', 'Bern','Valais', 'Vaud', 'Ticino', 'StGallen', 'Zurich',
                            'Fribourg', 'Luzern', 'Aargau', 'Uri', 'Thurgau', 'Schwyz', 'Jura', 'Neuchatel', 'Solothurn', 
                            'Glarus', 'BaselLandschaft', 'Obwalden', 'Nidwalden', 'Geneva', 'Schaffhausen', 'AppenzellAusserrhoden', 
                            'Zug', 'AppenzellInnerrhoden', 'BaselStadt']
    name_code = ['GR', 'BE', 'VS', 'VD', 'TI', 'SG', 'ZH', 'FR', 'LU', 'AG', 'UR', 'TG', 'SZ', 'JU', 'NE', 'SO', 'GL', 'BL', 'OW', 'NW', 'GE', 'SH', 'AR', 'ZG', 'AI', 'BS']

    calendar_name_code_dict = dict(zip(name_code, name_for_calendar))
    canton_name_for_calendar = calendar_name_code_dict.get(canton_code)        
    return canton_name_for_calendar, canton_code