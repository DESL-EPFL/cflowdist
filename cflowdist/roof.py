import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import openmeteo_requests
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .core import Location
    from geopandas import GeoDataFrame




def get_open_meteo(location: "Location", date_start:str, date_end:str) -> pd.DataFrame:
    """
    This function is originally provided by [Open-Meteo](https://open-meteo.com/en/docs#historical-weather-api) and adapted for our use case.
    Retrieve local weather data (GHI, DNI, DHI, temperature, and wind speed) for a given location and date range using the Open-Meteo API.
    The function sends a request to the Open-Meteo API with the specified parameters and processes the response to extract the relevant weather data.
    The resulting DataFrame contains the hourly weather data indexed by date and time.

    Parameters
    ----------
    location : Location
        A Location object containing the latitude and longitude of the location for which weather data is to be retrieved.
    date_start : str
        A string representing the start date for the weather data retrieval in the format 'YYYY-MM-DD'.
    date_end : str
        A string representing the end date for the weather data retrieval in the format 'YYYY-MM-DD'.

    Returns
    -------
    pd.DataFrame
        A DataFrame containing the hourly weather data indexed by date and time.

    """
    openmeteo = openmeteo_requests.Client()

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "start_date": date_start,
        "end_date": date_end,
        "timezone": 'Etc/GMT-1',
        "hourly": ["temperature_2m", "wind_speed_10m", "shortwave_radiation", "diffuse_radiation", "direct_normal_irradiance"],
        "wind_speed_unit": "ms"
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation: {response.Elevation()} m asl")
    # print(f'Timezone: {response.Timezone().decode("utf-8")} ({response.TimezoneAbbreviation().decode("utf-8")})')
    # print(f"Timezone difference to GMT+0: {response.UtcOffsetSeconds()} s")

    # Process hourly data. The order of variables needs to be the same as requested.
    hourly = response.Hourly()
    hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
    hourly_wind_speed_10m = hourly.Variables(1).ValuesAsNumpy()
    hourly_shortwave_radiation = hourly.Variables(2).ValuesAsNumpy()
    hourly_diffuse_radiation = hourly.Variables(3).ValuesAsNumpy()
    hourly_direct_normal_irradiance = hourly.Variables(4).ValuesAsNumpy()

    hourly_data = {"date": pd.date_range(
        start = pd.to_datetime(hourly.Time(), unit = "s"),
        end = pd.to_datetime(hourly.TimeEnd(), unit = "s"),
        freq = pd.Timedelta(seconds = hourly.Interval()),
        inclusive = "left",
        tz= response.Timezone().decode("utf-8")
    )}
    hourly_data["temperature_2m"] = hourly_temperature_2m
    hourly_data["wind_speed_10m"] = hourly_wind_speed_10m
    hourly_data["shortwave_radiation"] = hourly_shortwave_radiation
    hourly_data["diffuse_radiation"] = hourly_diffuse_radiation
    hourly_data["direct_normal_irradiance"] = hourly_direct_normal_irradiance

    openmeteo_df = pd.DataFrame(data = hourly_data)
    openmeteo_df.set_index('date',inplace=True)
    openmeteo_df.columns = ['T_2m', 'W_10m', 'GHI', 'DHI', 'DNI']
    return openmeteo_df#.tz_convert(tz)





def find_roof(pv_plant_df: "GeoDataFrame", roof_df: "GeoDataFrame") -> "GeoDataFrame":
    '''
    Find the nearest roof(s) and building (by SB_UUID) to which we can associate the pv plant concerned.
    The function uses a KDTree to efficiently find the nearest roof for each PV plant based on their geographic coordinates.
    The resulting DataFrame contains the PV plant information along with the associated roof information, indexed by the original index of the PV plant DataFrame.

    Parameters
    ----------
    pv_plant_df : GeoDataFrame
        A GeoDataFrame containing the geographic information of PV plants, including their coordinates (geometry) and other relevant attributes.
    roof_df : GeoDataFrame
        A GeoDataFrame containing the geographic information of roofs, including their coordinates (geometry) and other relevant attributes such as SB_UUID.

    Returns
    -------
    GeoDataFrame
        A GeoDataFrame containing the PV plant information along with the associated roof information, indexed by the original index of the PV plant DataFrame. The resulting DataFrame includes a new column 'SB_UUID' that indicates the associated roof's SB_UUID for each PV plant.
    '''
    if pv_plant_df.empty:
        return pv_plant_df
    
    assert pv_plant_df.geometry.crs == roof_df.geometry.crs, 'CRS must be the same.'
    
    nA = np.array(list(pv_plant_df.geometry.apply(lambda x: (x.x, x.y))))
    nB = np.array(list(roof_df.geometry.apply(lambda x: (x.x, x.y))))
    btree = cKDTree(nB)
    dist, idx = btree.query(nA, k=1)

    pv_plant_df.loc[:, 'SB_UUID'] = roof_df.loc[idx].SB_UUID.values
    pv_plant_df['xtf_id'] = pv_plant_df.index
    pv_roof = pv_plant_df.merge(roof_df,left_on='SB_UUID',right_on='SB_UUID')
    pv_roof.set_index('xtf_id',inplace=True)
    
    return pv_roof 