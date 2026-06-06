let initialBbox = [6.0, 45.85, 10.45, 47.70]; // Switzerland bounding box [west, south, east, north]

// const TileServerBaseURL = 'http://localhost:8080';
const Padding = window.innerWidth > 600 ? 60 : 20;

const scriptSrc = document.currentScript.src;
const scriptBase = scriptSrc.substring(0, scriptSrc.lastIndexOf('/') + 1);

const PMTILES_URL = "https://pub-0ce574d0b2974e848646f0c02f73f8dc.r2.dev/combined-sources.pmtiles";

const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

const map = new maplibregl.Map({
    container: 'map',
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
    bounds: initialBbox,
    fitBoundsOptions: {
        padding: Padding
    }
});

map.on('load', () => {
    map.addSource('data', {
        type: 'vector',
        url: `pmtiles://${PMTILES_URL}`
    });

    map.addLayer({
        id: 'mv_lines-layer',
        type: 'line',
        source: 'data',
        'source-layer': 'mv_lines',
        paint: {
            'line-color': 'white',
            'line-width': 2,
            'line-opacity': 0.7
        }
    });

    map.addLayer({
        id: 'lv_lines-layer',
        type: 'line',
        source: 'data',
        'source-layer': 'lv_lines',
        paint: {
            'line-color': 'gainsboro',
            'line-width': 1.5,
            'line-opacity': 1
        }
    });

    map.addLayer({
        id: 'mv_nodes-layer',
        type: 'circle',
        source: 'data',
        'source-layer': 'mv_nodes',
        paint: {
            "circle-radius": 4,
            "circle-color": "whitesmoke",
            "circle-opacity": 0.5,
            "circle-stroke-color": "white",
            "circle-stroke-width": 0.5
        }
    });


    map.addLayer({
        id: 'lv_nodes-layer',
        type: 'circle',
        source: 'data',
        'source-layer': 'lv_nodes',
        paint: {
            "circle-radius": 2.5,
            "circle-color": "whitesmoke",
            "circle-opacity": 0.5,
            "circle-stroke-color": "white",
            "circle-stroke-width": 0.5
        }
    });

    map.addLayer({
        id: 'plants-layer',
        type: 'circle',
        source: 'data',
        'source-layer': 'plants',
        paint: {
            "circle-radius": [
            "interpolate", ["linear"], ["get", "TotalPower"],
            0, 2,
            3, 3,
            10, 4,
            50, 6,
            100, 8,
            1000, 10,
            10000, 15,
            100000, 20
            ],
            "circle-color": [
            "match",
            ["get", "SubCategory"],

                "Hydroelectric power", "lightskyblue",          // Light Blue
                "Photovoltaic", "gold",        // Gold
                "Wind energy", "dodgerblue",               // Dodger Blue
                "Nuclear energy", "#ff4e50",              // Red/Orange
                "Natural gas", "coral",                 // Coral
                "Biomass", "forestgreen",                 // Forest Green
                "#cccccc"                          // Fallback color for unmatched items
            
            ],
            "circle-opacity": 0.7,
            "circle-stroke-color": "white",
            "circle-stroke-width": 0.5
        }
    });

    
});



// Tooltip popup
map.on('click', 'plants-layer', (e) => {
const Coordinates = e.features[0].geometry.coordinates.slice();
const Address = e.features[0].properties.Address || 'Unknown address';
const BeginOperation = e.features[0].properties.BeginningOfOperation || 'Unknown date';
const TotalPower = Math.round(e.features[0].properties.TotalPower) || 'Unknown power';
const Category = e.features[0].properties.SubCategory || 'Unknown category';

let popupContent = `
    <div class="popup-container">
        
        <table class="popup-table">
            <tr><th>Category</th><td>${Category}</td></tr>
            <tr><th>Address</th><td>${Address}</td></tr>
            <tr><th>Operation</th><td>${BeginOperation}</td></tr>
            <tr><th>Total Power</th><td>${TotalPower} kW</td></tr>
`;

if (Category === "Photovoltaic") {

    const RoofArea = Math.round(e.features[0].properties.Roof_Area) || 'Unknown';
    const RoofInclination = e.features[0].properties.Roof_Inclination || 'Unknown';
    const RoofOrientation = e.features[0].properties.Roof_Orientation || 'Unknown';
    popupContent += `
            <tr><th>Roof Area</th><td>${RoofArea} m²</td></tr>
            <tr><th>Roof Inclination</th><td>${RoofInclination}°</td></tr>
            <tr><th>Roof Orientation</th><td>${RoofOrientation}°</td></tr>
    `;
}

popupContent += `</table></div>`;


new maplibregl.Popup({ maxWidth: '300px' })
    .setLngLat(Coordinates)
    .setHTML(popupContent)
    .addTo(map);
});

// Change cursor on hover
map.on('mouseenter', 'plants-layer', () => {
map.getCanvas().style.cursor = 'pointer';
});
map.on('mouseleave', 'plants-layer', () => {
map.getCanvas().style.cursor = '';
});