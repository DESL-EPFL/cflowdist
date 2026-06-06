# CFlowDist

A Python toolkit for tracing carbon flows and allocating carbon intensity in Swiss distribution grids.  Models and data sources are described in our paper titled: *Carbon Flow Tracing in Distribution Grids: From Method to Application*.

## Documentation

The documentation is available at this [link](https://DESL-EPFL.github.io/cflowdist/). 



## Installation
Clone the repository via:
```bash
git clone https://github.com/DESL-EPFL/cflowdist.git carbonflow

```

Then switch to the directory:

```bash
cd carbonflow
```


A virtual environment is suggested:

On Windows:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

On Unix or MacOS:

```bash
python -m venv .venv
source .venv/bin/activate
```


Then install the package:
```bash
pip install -e .
```

## Using package

An example of using the package is provided in the Jupyter notebook `test/test.ipynb`. The following sections provide a quick overview of the main steps.


### Import modules

```{python}
import cflowdist as cfd
```

### Initiate an object

Initiate a `CarbonTracer` object by passing the address, it will be parsed into a geo-coordinate (longitude, latitude). Note that only locations in Switzerland are supported. Then the data of the grid that the coordinate is located in will be loaded.
```{python}
# init
tracer = cfd.CarbonTracer(address = '8305 Dietlikon')
```

### Visualize the network

```{python}
# visualize
tracer.network_plot()
```

### Access the grid

The `pandapower` grid object can be accessed via:
```{python}
tracer.pp_grid
```


### Initiate snapshots

The hourly snapshots to analyze need to be set. Note that only year 2023 is supported.
```{python}
# init snapshots
t_start = '2023-06-08 12:00:00'
t_end = '2023-06-08 14:00:00'
snapshots = tracer.set_snapshots(t_start=t_start, t_end=t_end)
```

### Run power flow

The load and generation profiles are generated before exectution of the AC power flow calculation.
```{python}
# power flow
tracer.power_flow()
```

### Run carbon allocation

Allocate the carbon intensity using the dedicated method. You can choose which allocation method to use via the parameters `loss_allocation` and `self_consumption`.
```{python}
# carbon allocation
node_ci_df_no_loss = tracer.allocate_carbon(
    loss_allocation=False,
    self_consumption=True
    )
```

Check the carbon intensity results aggregated at network level:
```{python}
tracer.net_ci_df.round(2)
```

### Visualize the results
```{python}
tracer.network_carbon_plot(snapshot=snapshots[1], show_tools=True)
```

### IO

Export an object using pickle — Python object serialization.
```python
tracer.save_pickle('./result/docs-example/Dietlikon20230608.pkl')
```