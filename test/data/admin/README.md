## Electricity production plants

The Swiss electricity production plants dataset is provided by the Swiss Federal Office of Energy (SFOE) and can be accessed through the [link](https://opendata.swiss/en/dataset/elektrizitatsproduktionsanlagen). The suitability of roofs for the use of solar energy is provided by SFOE and can be accessed through the [link](https://opendata.swiss/en/dataset/eignung-von-hausdachern-fur-die-nutzung-von-sonnenenergie). We have preprocessed the original data, match the roof information with the photovoltaic plants and saved it as a parquet file `plants_with_roof.parquet` for easier loading. Please respect the [Terms of Use](https://opendata.swiss/en/terms-of-use) of the original data source.


## Land Use Statistics

The Swiss Land use statistics dataset is provided by the Swiss Federal Statistical Office (FSO) and can be accessed through their [website](https://www.bfs.admin.ch/bfs/en/home/services/geostat/swiss-federal-statistics-geodata/land-use-cover-suitability/swiss-land-use-statistics.html). The nomenclature of the land use categories `NOLU04` comes from this [link](https://www.bfs.admin.ch/bfs/de/home/statistiken/raum-umwelt/nomenklaturen/arealstatistik.html).

We have preprocessed the land use data and saved it as a parquet file `lu.parquet` for easier loading. Please respect the [Terms of Use](https://www.bfs.admin.ch/bfs/en/home/bfs/bundesamt-statistik/nutzungsbedingungen.html) of the original data source.