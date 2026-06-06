import folium
import folium.plugins
from folium.plugins import TimeSliderChoropleth
import branca
import branca.colormap as cm
from geopandas import points_from_xy
import geopandas as gpd
from shapely.geometry import LineString
import pandas as pd
import numpy as np

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .core import CarbonTracer


def row_to_html(row):
    df = pd.DataFrame(row, index=row.index)
    df.columns = [""]
    return df.style.set_table_attributes('class="table table-striped table-hover table-condensed table-responsive"').set_table_styles([{'selector': ' th', 'props': [('vertical-align', 'middle')]}]).to_html()

def prepare_node_popup(node_gdf):
    namesplit = pd.DataFrame([i[1].split('_node_') for i in node_gdf.name.str.split('bus_')], columns = ['Network ID','Node ID'])
    node_gdf = pd.concat([node_gdf,namesplit], axis = 1)
    columns_print = ['Network ID','Node ID', 'Landuse Category']
    if 'co2_intensity' in node_gdf.columns:
        node_gdf['CO2 Intensity'] = node_gdf['co2_intensity'].round(2).astype(str) + ' gCO2eq/kWh'
        columns_print.append('CO2 Intensity')
    if 'co2_intensity' in node_gdf.columns:
        node_gdf['CO2 Emission'] = node_gdf['co2_emission'].round(3).astype(str) + ' kgCO2eq/h'
        columns_print.append('CO2 Emission')
    node_gdf['popuphtml'] = node_gdf[columns_print].apply(row_to_html, axis=1)
    return node_gdf
def prepare_plant_popup(plant_df):
    namesplit = pd.DataFrame([i[1].split('_node_') for i in plant_df.bus_name.str.split('bus_')], columns = ['Network ID','Node ID'])
    plant_df['Plant ID'] = plant_df['xtf_id']
    plant_df = pd.concat([plant_df,namesplit], axis = 1)
    plant_df['Capacity'] = plant_df['TotalPower'].round(1).astype(str) + ' kW'
    plant_df['Type'] =  plant_df['SubCategory']


    columns_print = ['Plant ID', 'Network ID','Node ID', 'Capacity', 'Type']

    plant_df['popuphtml'] = plant_df[columns_print].apply(row_to_html, axis=1)
    return plant_df

    

def prepare_node_gdf(pp_grid):
    node_geometry = points_from_xy(x= pp_grid.bus_geodata.x, y = pp_grid.bus_geodata.y, crs='epsg:2056')
    node_gdf = gpd.GeoDataFrame(data=pp_grid.bus.name, geometry=node_geometry, crs='epsg:2056')
    node_gdf['Landuse Category'] = pp_grid.bus['landuse']
    return node_gdf

def prepare_line_gdf(pp_grid):
    line_geometry = pp_grid.line_geodata['coords'].apply(lambda x: LineString(x))
    line_gdf = gpd.GeoDataFrame(data=pp_grid.line.name, geometry=line_geometry.sort_index(), crs='epsg:2056')
    return line_gdf

def prepare_plant_gdf(mv_plant_df):
    plant_gdf = mv_plant_df
    plant_gdf = plant_gdf.drop(columns='BeginningOfOperation').to_crs(epsg='2056')
    plant_gdf.reset_index(inplace = True)
    return plant_gdf
        


def add_elements_to_plot(m, node_gdf, line_gdf, plant_gdf, show_colormap = True, fill_circle = True, add_lv_internal:bool=True):
        
    # linear = cm.LinearColormap(["green", "yellow", "red"], 
    #                             vmin= 10, 
    #                             #vmax=tracer.pypsa_net.carriers.co2_emissions.loc[tracer.mv_plant_df.SubCategory.unique()].max()
    #                             vmax= 100
    #                             )
    linear = cm.LinearColormap(["blue","green", "yellow", "orange","red","brown"], vmin=10, vmax=110)

    
    # HV bus
    folium.GeoJson(
            node_gdf[node_gdf['name'].str.startswith('bus_HV')],
            name="Nodes",
            marker=folium.Circle(radius=4, fill_color="green", fill_opacity=0.4, color="black", weight=1, fill = fill_circle),
            # tooltip=folium.GeoJsonTooltip(fields=["name"]),
            popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False) if fill_circle else None,
            style_function=lambda x: {
                "fillColor": linear(x['properties']["co2_intensity"]) if fill_circle else None,
                "radius": 30,
            },
            highlight_function=lambda x: {"fillOpacity": 0.8},
            #zoom_on_click=True,
        ).add_to(m)

    # MV buses
    folium.GeoJson(
    node_gdf[node_gdf['name'].str.startswith('bus_MV')],
    name="Nodes",
    marker=folium.Circle(radius=4, fill_color="orangered", fill_opacity=0.4, color="black", weight=1, fill = fill_circle),
    # tooltip=folium.GeoJsonTooltip(fields=["name"]),
    popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False) if fill_circle else None,
    style_function=lambda x: {
        "fillColor": linear(x['properties']["co2_intensity"]) if fill_circle else None,
        "radius": 13,
    },
    highlight_function=lambda x: {"fillOpacity": 0.8},
    # zoom_on_click=True,
    ).add_to(m)

    if add_lv_internal:
        # LV buses
        folium.GeoJson(
            node_gdf[node_gdf['name'].str.startswith('bus_LV')],
            name="Nodes",
            marker=folium.Circle(radius=4, fill_color="orange", fill_opacity=0.4, color="dimgrey", weight=1, opacity = 0.7, fill = fill_circle),
            #tooltip=folium.GeoJsonTooltip(fields=["name"]),
            popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False) if fill_circle else None,
            style_function=lambda x: {
                "fillColor": linear(x['properties']["co2_intensity"]) if fill_circle else None,
                "radius": 8,
            },
            highlight_function=lambda x: {"fillOpacity": 0.8},
            # zoom_on_click=True,
        ).add_to(m)

    
    size_max_plants = 40
    max_power = plant_gdf.TotalPower.max()
    plant_gdf['size'] = plant_gdf['TotalPower']/max_power * size_max_plants + 3

    # Plants
    folium.GeoJson(
        plant_gdf,
        name="Plants",
        marker=folium.Circle(radius=4, fill_color="gold", fill_opacity=0.8, color="gold", weight=1),
        # tooltip=folium.GeoJsonTooltip(fields=["name"]),
        popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False),
        style_function=lambda x: {
            "fillColor": 'gold',
            "radius": (x['properties']['size']),
        },
        highlight_function=lambda x: {"fillOpacity": 0.8},
        # zoom_on_click=True,
    ).add_to(m)

    edge_geometry = line_gdf[line_gdf['name'].str.startswith('MV')].geometry
    raw_edges = [list(i.coords) for i in edge_geometry.to_crs(epsg=4326)]
    raw_edges = [[[i[1], i[0]] for i in j] for j in raw_edges]

    folium.PolyLine(
                locations=raw_edges,
                color="black",
                weight=1.5,
                opacity=1,
            ).add_to(m)


    if add_lv_internal:
        edge_geometry = line_gdf[line_gdf['name'].str.startswith('LV')].geometry
        raw_edges = [list(i.coords) for i in edge_geometry.to_crs(epsg=4326)]
        raw_edges = [[[i[1], i[0]] for i in j] for j in raw_edges]

        folium.PolyLine(
                    locations=raw_edges,
                    color="dimgrey",
                    weight=1,
                    opacity=0.7,
                ).add_to(m)
    linear.caption = "Carbon Intensity (gCO2/kWh)"
    if show_colormap:
        m.add_child(linear)

def add_tools(m):
    folium.plugins.Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True,
    ).add_to(m)

    folium.plugins.Geocoder(position="bottomleft").add_to(m)

def network_plot(tracer: "CarbonTracer", show_tools: bool= True) -> folium.Map:
    """
    Plot network topology by folium, including HV, MV and LV buses, generation plants, as well as MV and LV lines.

    Parameters
    ------
    tracer: CarbonTracer
        The CarbonTracer object that contains the constructed network data.
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
    m = folium.Map(location=[tracer.loc_selected.latitude, tracer.loc_selected.longitude], zoom_start=15, tiles='cartodb voyager')
    line_gdf = prepare_line_gdf(tracer.pp_grid)
    node_gdf = prepare_node_gdf(tracer.pp_grid)
    node_gdf = prepare_node_popup(node_gdf)
    kw = {"prefix": "fa", "color": "red", "icon": "street-view"}
    icon = folium.Icon(angle=0, **kw)
    folium.Marker(location=[tracer.loc_selected.latitude,tracer.loc_selected.longitude], 
                    icon=icon,tooltip='Location selected',
                    popup=tracer.loc_selected.address).add_to(m)
    
    # HV buses
    folium.GeoJson(
        node_gdf[node_gdf['name'].str.startswith('bus_HV')],
        name="Nodes",
        marker=folium.Circle(radius=4, fill_color="blueviolet", fill_opacity=0.4, color="black", weight=1),
        # tooltip=folium.GeoJsonTooltip(fields=["name"]),
        popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False),
        style_function=lambda x: {
            "fillColor": 'blueviolet',
            "radius": 30,
        },
        highlight_function=lambda x: {"fillOpacity": 0.8},
        #zoom_on_click=True,
    ).add_to(m)

    # MV buses
    folium.GeoJson(
        node_gdf[node_gdf['name'].str.startswith('bus_MV')],
        name="Nodes",
        marker=folium.Circle(radius=4, fill_color="dodgerblue", fill_opacity=0.4, color="black", weight=1),
        # tooltip=folium.GeoJsonTooltip(fields=["name"]),
        popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False),
        style_function=lambda x: {
            "fillColor": 'dodgerblue',
            "radius": 15,
        },
        highlight_function=lambda x: {"fillOpacity": 0.8},
        # zoom_on_click=True,
    ).add_to(m)

    # LV buses
    folium.GeoJson(
        node_gdf[node_gdf['name'].str.startswith('bus_LV')],
        name="Nodes",
        marker=folium.Circle(radius=4, fill_color="aqua", fill_opacity=0.4, color="dimgrey", weight=1),
        #tooltip=folium.GeoJsonTooltip(fields=["name"]),
        popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False),
        style_function=lambda x: {
            "fillColor": 'aqua',
            "radius": 7,
        },
        highlight_function=lambda x: {"fillOpacity": 0.8},
        # zoom_on_click=True,
    ).add_to(m)

    # plants_gdf = tracer.mv_plant_df
    # plants_gdf = plants_gdf.drop(columns='BeginningOfOperation').to_crs(epsg='2056')
    # plants_gdf.reset_index(inplace = True)
    plant_gdf = prepare_plant_gdf(tracer.mv_plant_df)
    size_max_plants = 40
    max_power = plant_gdf.TotalPower.max()
    plant_gdf['size'] = plant_gdf['TotalPower']/max_power * size_max_plants + 1
    plant_gdf = prepare_plant_popup(plant_gdf)

    # Plants
    folium.GeoJson(
        plant_gdf,
        name="Plants",
        marker=folium.Circle(radius=4, fill_color="gold", fill_opacity=0.8, color="gold", weight=1),
        # tooltip=folium.GeoJsonTooltip(fields=["name"]),
        popup=folium.GeoJsonPopup(fields=["popuphtml"], labels= False),
        style_function=lambda x: {
            "fillColor": 'gold',
            "radius": (x['properties']['size']),
        },
        highlight_function=lambda x: {"fillOpacity": 0.8},
        # zoom_on_click=True,
    ).add_to(m)

    edge_geometry = line_gdf[line_gdf['name'].str.startswith('MV')].geometry
    raw_edges = [list(i.coords) for i in edge_geometry.to_crs(epsg=4326)]
    raw_edges = [[[i[1], i[0]] for i in j] for j in raw_edges]

    folium.PolyLine(
                locations=raw_edges,
                color="black",
                weight=1.5,
                opacity=1,
            ).add_to(m)


    edge_geometry = line_gdf[line_gdf['name'].str.startswith('LV')].geometry
    raw_edges = [list(i.coords) for i in edge_geometry.to_crs(epsg=4326)]
    raw_edges = [[[i[1], i[0]] for i in j] for j in raw_edges]

    folium.PolyLine(
                locations=raw_edges,
                color="dimgrey",
                weight=1.5,
                opacity=1,
            ).add_to(m)
    if show_tools:
        add_tools(m=m)

    return m


def network_carbon_plot(tracer: "CarbonTracer", snapshot: pd.Timestamp, show_colormap: bool = True, show_tools: bool= True) -> folium.Map:
    """
    Plot the calculated node-level carbon intensity using folium.

    Parameters
    ------
    tracer: CarbonTracer
        The CarbonTracer object that contains the constructed network data.
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
    m = folium.Map(location=[tracer.loc_selected.latitude, tracer.loc_selected.longitude], zoom_start=14, tiles = 'cartodb positron')
    kw = {"prefix": "fa", "color": "red", "icon": "street-view"}
    icon = folium.Icon(angle=0, **kw)
    folium.Marker(location=[tracer.loc_selected.latitude,tracer.loc_selected.longitude], 
                    icon=icon,tooltip='Location selected',
                    popup=tracer.loc_selected.address).add_to(m)
    line_gdf = prepare_line_gdf(pp_grid=tracer.pp_grid)
    node_gdf = prepare_node_gdf(pp_grid=tracer.pp_grid)
    node_gdf['co2_intensity'] = tracer.node_ci_df.loc[snapshot].values
    node_gdf['co2_emission'] = tracer.node_ce_df.loc[snapshot].values
    node_gdf = prepare_node_popup(node_gdf)
    # node_gdf = node_gdf[node_gdf.co2_intensity != 0]    
    plant_gdf = prepare_plant_gdf(mv_plant_df=tracer.mv_plant_df)
    plant_gdf = prepare_plant_popup(plant_gdf)
    
    add_elements_to_plot(m = m, node_gdf=node_gdf, line_gdf=line_gdf, plant_gdf=plant_gdf, show_colormap=show_colormap)
    if show_tools:
        add_tools(m=m)

    return m

def network_dual_plot(tracer: "CarbonTracer", snapshot_night: pd.Timestamp, snapshot_day: pd.Timestamp, show_colormap: bool = False) -> folium.plugins.DualMap:
    """
    Plot the calculated node-level carbon intensity using folium dual map, comparing two snapshots horizontally, one with light style tile and one with dark style tile.

    Parameters
    ------
    tracer: CarbonTracer
        The CarbonTracer object that contains the constructed network data.
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
    m = folium.plugins.DualMap(location=[tracer.loc_selected.latitude, tracer.loc_selected.longitude], zoom_start=14,tiles = None)
    folium.TileLayer('cartodb dark_matter').add_to(m.m1)
    folium.TileLayer('cartodb positron').add_to(m.m2)

    folium.Marker(location=[tracer.loc_selected.latitude,tracer.loc_selected.longitude], 
                    icon=folium.Icon('red'),tooltip='Location selected',
                    popup=tracer.loc_selected.address).add_to(m.m1)
    folium.Marker(location=[tracer.loc_selected.latitude,tracer.loc_selected.longitude], 
                    icon=folium.Icon('red'),tooltip='Location selected',
                    popup=tracer.loc_selected.address).add_to(m.m2)

    line_gdf = prepare_line_gdf(pp_grid=tracer.pp_grid)
    node_gdf = prepare_node_gdf(pp_grid=tracer.pp_grid)
    node_gdf['co2_intensity'] = tracer.node_ci_df.loc[snapshot_night].values
    node_gdf['co2_emission'] = tracer.node_ce_df.loc[snapshot_night].values
    node_gdf = prepare_node_popup(node_gdf)
    # node_gdf = node_gdf[node_gdf.co2_intensity != 0]    
    plant_gdf = prepare_plant_gdf(mv_plant_df=tracer.mv_plant_df)
    plant_gdf = prepare_plant_popup(plant_gdf)
    add_elements_to_plot(m = m.m1, node_gdf=node_gdf, line_gdf=line_gdf, plant_gdf=plant_gdf, show_colormap = False)
    
    node_gdf = prepare_node_gdf(pp_grid=tracer.pp_grid)
    node_gdf['co2_intensity'] = tracer.node_ci_df.loc[snapshot_day].values
    node_gdf['co2_emission'] = tracer.node_ce_df.loc[snapshot_day].values
    node_gdf = prepare_node_popup(node_gdf)
    add_elements_to_plot(m = m.m2, node_gdf=node_gdf, line_gdf=line_gdf, plant_gdf=plant_gdf, show_colormap = True)

    return m

def lv_grids_time_plot(tracer: "CarbonTracer", tile_name: str = 'white', show_tools:bool=False) -> folium.Map:
    """
    Plot the calculated carbon intensity aggegated to a LV-net level using folium TimeSliderChoropleth, with a time slider.

    Parameters
    ------
    tracer: CarbonTracer
        The CarbonTracer object that contains the constructed network data.
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

    # Note: Here we use Unix epoch, Unix timestamps abstract away any timezone considerations since it is inherently time-zone independent.
    result = tracer.net_ci_df
    duplicates = result.index.duplicated()
    if duplicates.any():
        idx_int = np.where(duplicates)[0][0]
        idx_list = result.index.to_list()
        idx_list[idx_int]+=pd.Timedelta(minutes=10)
        result.index = idx_list
    lv_ids = result.columns[result.columns.str.startswith('LV_')]
    lv_ids = [id.split('_', maxsplit=1)[1] for id in lv_ids]
    # lv_hull_dict = {}
    # for area in tracer.lv_hulls:
    #     for id, hull in tracer.lv_hulls[area].items():
    #         lv_hull_dict[id] = hull
    # hull_gdf = gpd.GeoDataFrame({'name':lv_ids, 'geometry': [shapely.Polygon(lv_hull_dict.get(id)) for id in lv_ids]}, crs='epsg:2056')
    hull_gdf = tracer.lv_hulls_gdf
    hull_gdf = hull_gdf[hull_gdf.id.isin(lv_ids)]
    dt_index_epochs = result.index.astype("int64") // 10 ** 9
    dt_index = dt_index_epochs.astype("U10")
    styledata = {}
    for net_id in hull_gdf.id.values:
        df = pd.DataFrame(
            {
                "color": result.loc[:,result.columns[result.columns.str.endswith(net_id)][0]].values,
                "opacity": 0.6,
            },
            index=dt_index,
        )
        styledata[net_id] = df
    hull_gdf.index = hull_gdf.id.values

    max_color, min_color, = 0, 0

    # for net_id, data in styledata.items():
    #     max_color = max(max_color, data["color"].max())
    #     min_color = min(max_color, data["color"].min())
    
    # cmap = cm.LinearColormap(['green', 'yellow', 'red'], vmin = 10, vmax = 100)
    cmap = cm.LinearColormap(["blue","green", "yellow", "orange","red","brown"], vmin=10, vmax=110)



    for net_id, data in styledata.items():
        data["color"] = data["color"].apply(cmap)
        data["opacity"] = 0.5

    styledict = {
        str(net_id): data.to_dict(orient="index") for net_id, data in styledata.items()
    }
    if tile_name == 'white':
        # Create a white image of 4 pixels, and embed it in a url.
        white_tile = branca.utilities.image_to_url([[1, 1], [1, 1]])

        # Create a map using this url for each tile.
        m = folium.Map(location=[tracer.loc_selected.latitude, tracer.loc_selected.longitude], zoom_start=14, tiles=white_tile, attr='White')

    else:
        m = folium.Map(location=[tracer.loc_selected.latitude, tracer.loc_selected.longitude], zoom_start=14, tiles='cartodb positron')

    kw = {"prefix": "fa", "color": "red", "icon": "street-view"}
    icon = folium.Icon(angle=0, **kw)
    folium.Marker(location=[tracer.loc_selected.latitude,tracer.loc_selected.longitude], 
                    icon=icon,tooltip='Location selected',
                    popup=tracer.loc_selected.address).add_to(m)
    
    TimeSliderChoropleth(
        hull_gdf.to_json(),
        styledict=styledict,
        date_options = "ddd MMM DD YYYY, HH:mm"
    ).add_to(m)
    
    line_gdf = prepare_line_gdf(pp_grid=tracer.pp_grid)
    node_gdf = prepare_node_gdf(pp_grid=tracer.pp_grid)
    node_gdf['co2_intensity'] = -1
    
    plant_gdf = prepare_plant_gdf(mv_plant_df=tracer.mv_plant_df)
    plant_gdf = prepare_plant_popup(plant_gdf)
    add_elements_to_plot(m = m, node_gdf=node_gdf, line_gdf=line_gdf, plant_gdf=plant_gdf, show_colormap=False, fill_circle=False, add_lv_internal=False)

    cmap.caption = "Carbon Intensity (gCO2/kWh)"
    m.add_child(cmap)
    if show_tools:
        add_tools(m=m)
    return m
