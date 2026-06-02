// A limited public token of mapbox. to let it work in your domain, create your own token.
const MapboxToken = 'pk.eyJ1Ijoid2VueXUtbGl1IiwiYSI6ImNtcHdtcTl6ZDAyZjEycnM2d3A0cGEwNnUifQ.C3D5Pbubts2lPUtBIzuCDw';
const Padding =  window.innerWidth > 800 ? 100 : 50;

let nodeGeoData, lineGeoData,  hullGeoData, nodeCIData, nodeCEData, netCIData, netCEData;

let needleGeoJson, groundGeoJson;

let activeTimeIndex = 0;
let isAnimating = false;
let timeKeys = [];

const ANIMATION_SPEED = 0.08;


let map;

let meteoData, meteoDescriptions;

let initialBbox;

let initialCenter;


const ColorExpression = [
    'interpolate', ['linear'], ['get', 'current_intensity'],
    10, 'blue',
    30, 'green',
    50, 'orange',
    70, 'red',
    90, 'brown'
];

function changeLegendColor(value) {
    // Select all text elements inside your SVG container
    const allTexts = document.querySelectorAll('#svg-colormap-container text');

    // Loop through and change the fill color
    allTexts.forEach(textNode => {
        textNode.setAttribute('fill', value); 
    });
}

function getLightPreset(timestamp, sunrise_timestamp, sunset_timestamp) {
    const CurrentHour = new Date(parseInt(timestamp)).getHours();
    const SunriseHour = new Date(parseInt(sunrise_timestamp)).getHours();
    const SunsetHour = new Date(parseInt(sunset_timestamp)).getHours();

    // const isDay = (CurrentHour >= SunriseHour-2) && (CurrentHour < SunsetHour+2);
    if ((CurrentHour > SunriseHour) && (CurrentHour <= SunriseHour+2)) {
        changeLegendColor('black');
        return 'dawn';
    }
    else if ((CurrentHour > SunriseHour+2) && (CurrentHour <= SunsetHour-2)) {
        changeLegendColor('black');
        return 'day';
    }
    else if ((CurrentHour > SunsetHour-2) && (CurrentHour < SunsetHour+2)) {
        changeLegendColor('white');
        return 'dusk';
    }
    else {
        changeLegendColor('white');
        return 'night';
    }
}

function createNeedleFootprint(lng, lat, size = 0.0001) {
    return [
        [lng - size, lat - size],
        [lng + size, lat - size],
        [lng + size, lat + size],
        [lng - size, lat + size],
        [lng - size, lat - size]
    ];
}

async function loadMap() {
    const [nodeGeoResponse, lineGeoResponse, plantResponse, hullGeoResponse, nodeCIResponse, nodeCEResponse, netCIResponse, netCEResponse] = await Promise.all([
        fetch('./nodes.geojson'),
        fetch('./lines.geojson'),
        fetch('./plants.geojson'),
        fetch('./hulls.geojson'),
        fetch('./summer/node_ci.json'),
        fetch('./summer/node_ce.json'),
        fetch('./summer/lv_net_ci.json'),
        fetch('./summer/lv_net_ce.json')
    ]);

    

    nodeGeoData = await nodeGeoResponse.json();
    lineGeoData = await lineGeoResponse.json();
    plantGeoData = await plantResponse.json();
    hullGeoData = await hullGeoResponse.json();
    nodeCIData = await nodeCIResponse.json();
    nodeCEData = await nodeCEResponse.json();
    netCIData = await netCIResponse.json();
    netCEData = await netCEResponse.json();

    timeKeys = Object.keys(nodeCIData).sort((a, b) => parseInt(a) - parseInt(b));

    initialCenter = turf.center(nodeGeoData).geometry.coordinates;

    const date_start = new Date(parseInt(timeKeys[0]));
    const date_end = new Date(parseInt(timeKeys[timeKeys.length - 1]));
    // format to 'YYYY-MM-DD', convert to local time Europe/Berlin
    const date_start_fmt = date_start.toLocaleDateString('en-CA', { timeZone: 'Europe/Zurich' });
    const date_end_fmt = date_end.toLocaleDateString('en-CA', { timeZone: 'Europe/Zurich' });   




    const meteoResponse = await fetch(`https://archive-api.open-meteo.com/v1/archive?latitude=${initialCenter[1]}&longitude=${initialCenter[0]}&start_date=${date_start_fmt}&end_date=${date_end_fmt}&hourly=weather_code,is_day&daily=sunrise,sunset&timezone=auto`);
    meteoData = await meteoResponse.json();

    const meteoDescResponse = await fetch('./descriptions.json');
    meteoDescriptions = await meteoDescResponse.json();

    // daily sunrise/sunset data, save key as 'YYYY-MM-DD' for easy lookup
    meteoData.dailySunMapper = {};
    for (let i = 0; i < meteoData.daily.time.length; i++) {
        const date = new Date(meteoData.daily.time[i]).toLocaleDateString('en-CA', { timeZone: 'Europe/Zurich' });
        meteoData.dailySunMapper[date] = {
            sunrise: new Date(meteoData.daily.sunrise[i]).getTime(),
            sunset: new Date(meteoData.daily.sunset[i]).getTime()
        };
    }

    // create weather code and is_day mapping for quick lookup
    meteoData.weatherMapper = {};

    const RainCodes = [51, 52, 53, 54, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82];
    const SnowCodes = [71, 73, 75, 77, 85, 86];
    for (let i = 0; i < meteoData.hourly.time.length; i++) {
        const timestamp = new Date(meteoData.hourly.time[i]).getTime();
        const dateKey = new Date(timestamp).toLocaleDateString('en-CA', { timeZone: 'Europe/Zurich' });
        meteoData.weatherMapper[timestamp] = {
            code: meteoData.hourly.weather_code[i],
            is_day: meteoData.hourly.is_day[i],
            is_rain: RainCodes.includes(parseInt(meteoData.hourly.weather_code[i])), // Rain codes
            is_snow: SnowCodes.includes(parseInt(meteoData.hourly.weather_code[i])),
            sunrise: meteoData.dailySunMapper[dateKey].sunrise,
            sunset: meteoData.dailySunMapper[dateKey].sunset
        };
    }

    initializeMap();
}


function initializeMap() {


    mapboxgl.accessToken = MapboxToken;

    map = new mapboxgl.Map({
        container: 'map',
        style: 'mapbox://styles/mapbox/standard',
        config: {
            basemap: {
                lightPreset: getLightPreset(timeKeys[0], meteoData.weatherMapper[timeKeys[0]].sunrise, meteoData.weatherMapper[timeKeys[0]].sunset)
            }
        },
        center: initialCenter,
        zoom: 13.8,
        pitch: 55,
    });

    map.on('load', () => {


        const plantCircleFeatures = plantGeoData.features.map(feature => {
            const center = feature.geometry.coordinates;
            const power = feature.properties.TotalPower;
            const radius = 0.02 * Math.sqrt(power/200) + 0.01; // Scale radius by power (adjust the multiplier as needed)
            const circle = turf.circle(center, radius, { units: 'kilometers', steps: 32 });
            return {
                "type": "Feature",
                "properties": feature.properties,
                "geometry": circle.geometry
            };
        });


        // 2. Prepare the Needle Source
        // We iterate through our polygons, find their centers, and create tiny squares
        const needleFeatures = hullGeoData.features.map((f, index) => {
            // For simplicity, using first coord as center. Use @turf/centroid for accuracy.
            const center = turf.centroid(f).geometry.coordinates;
            const lv_net_id = f.properties.id; // Start with the first time step
            const initialEmission = netCEData[timeKeys[0]][lv_net_id]; // Start with the first time step
            const initialIntensity = netCIData[timeKeys[0]][lv_net_id]; // Start with the first time step
            const radius = 0.02;
            const circle = turf.circle(center, radius, { units: 'kilometers', steps: 6 });
            return {
                "type": "Feature",
                "properties": {
                    "ce_series": timeKeys.map(key => netCEData[key][lv_net_id]), // The full time series for this feature
                    "ci_series": timeKeys.map(key => netCIData[key][lv_net_id]), // The full time series for this feature
                    "current_emission": initialEmission, // The animation frame value
                    "target_emission": initialEmission,   // The goal value
                    "current_intensity": initialIntensity, // For color coding
                    "target_intensity": initialIntensity   // For color coding
                },
                "geometry": circle.geometry
            };
        });

        const groundFeatures = hullGeoData.features.map((f) => {
            const center = turf.centroid(f).geometry.coordinates;
            const lv_net_id = f.properties.id; // Start with the first time step
            const initialIntensity = netCIData[timeKeys[0]][lv_net_id]; // Start with the first time step
            return {
                "type": "Feature",

                "properties": {
                    "ci_series": timeKeys.map(key => netCIData[key][lv_net_id]), // The full time series for this feature
                    "current_intensity": initialIntensity, // The animation frame value
                    "target_intensity": initialIntensity   // The goal value
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": f.geometry.coordinates
                }
            };
        });

        needleGeoJSON = { "type": "FeatureCollection", "features": needleFeatures };
        groundGeoJSON = { "type": "FeatureCollection", "features": groundFeatures };
        const plantGeoJSON = { "type": "FeatureCollection", "features": plantCircleFeatures };


        map.addSource('nodes', {
            type: 'geojson',
            data: nodeGeoData,
            promoteId: 'name',
        });

        map.addSource('lines', {
            type: 'geojson',
            data: lineGeoData
        });

        map.addSource('polygons', { type: 'geojson', data: groundGeoJSON });
        map.addSource('needles', { type: 'geojson', data: needleGeoJSON });
        map.addSource('plants', { type: 'geojson', data: plantGeoJSON });



        map.addLayer({
            id: 'lines-layer',
            type: 'line',
            source: 'lines',
            paint: {
                'line-color': '#888',
                'line-width': 2
            }
        });

        map.addLayer({
            'id': 'plant-layer',
            'type': 'fill',
            'source': 'plants',
            paint: {
                'fill-color': 'gold',
                'fill-opacity': 0.8,
                'fill-outline-color': '#000',
            }
        });

        map.addLayer({
            id: 'nodes-layer',
            type: 'circle',
            source: 'nodes',
            paint: {
                'circle-radius': 3,
                'circle-color': ColorExpression,
                'circle-stroke-width': 1,
                'circle-stroke-color': '#000',
                'circle-opacity': 0.8,
                'circle-emissive-strength': 1
            }
        });


        map.addLayer({
            'id': 'ground-layer',
            'type': 'fill',
            'source': 'polygons',
            'paint': {
                'fill-color': ColorExpression,
                'fill-opacity': 0.3,
                'fill-emissive-strength': 1
            },
            layout: {
                'visibility': 'none'
            }
        });

        // 4. Add the Needles (Extrusions)
        map.addLayer({
            'id': 'needle-layer',
            'type': 'fill-extrusion',
            'source': 'needles',
            'paint': {
                // Height is calculated from the emission property
                // Multiplied by a factor (e.g., 50) to make it visible on the map scale
                'fill-extrusion-height': ['*', ['get', 'current_emission'], 50],
                'fill-extrusion-base': 0,
                // Color ramp: Green for low, Red for high, intensity
                'fill-extrusion-color': ColorExpression,
                'fill-extrusion-opacity': 0.5,
                'fill-extrusion-emissive-strength': 1
            },
            'layout': {
                'visibility': 'none'
            }

        });
        
        setupVisibilityToggle();
        setupSlider();

    });

}

// function setupSlider() {
//     const slider = document.getElementById('slider');
//     const label = document.getElementById('time-label');
//     const datavalue = document.getElementById('weather-value');

//     slider.max = timeKeys.length - 1;

//     slider.addEventListener('input', (e) => {
//         const index = parseInt(e.target.value);
//         const timestamp = timeKeys[index];
        
//         // 1. Update Label (Human readable)
//         const date = new Date(parseInt(timestamp));
//         label.innerText = date.toLocaleString('en-CA', { 
//             month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' 
//         });

//         const WeatherCode = meteoData.weatherMapper[timestamp].code;
//         const IsDay = meteoData.weatherMapper[timestamp].is_day ? 'day' : 'night';
//         const WeatherText = meteoDescriptions[WeatherCode][IsDay].description;
//         const WeatherIcon = meteoDescriptions[WeatherCode][IsDay].image;


//         // Update 

//         needleGeoJSON.features.forEach(feature => {
//             feature.properties.target_emission = feature.properties.ce_series[index];
//             feature.properties.target_intensity = feature.properties.ci_series[index]; // Update target intensity as well
//         });
//         groundGeoJSON.features.forEach(feature => {
//             feature.properties.target_intensity = feature.properties.ci_series[index];
//         });

//         // Fire up the animation loop if it isn't already running
//         if (!isAnimating) {
//             isAnimating = true;
//             animateFrames();
//         }


//         datavalue.innerHTML = `
//             <img class="weather-icon" src=${WeatherIcon}>  ${WeatherText}
//         `;

//         // 2. Update Map
//         updateMapColors(timestamp);
//         updateBaseMapStyle(timestamp);
//         updateWeather(timestamp);


//     });

//     // Trigger first frame
//     slider.dispatchEvent(new Event('input'));
// }
function dateFormat(timestamp) {
    const date = new Date(parseInt(timestamp));
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear().toString();
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

function setupSlider() {
    const slider = document.getElementById('slider');
    const label = document.getElementById('time-label');
    const datavalue = document.getElementById('weather-value');
    // 👇 Grab your play button
    const playButton = document.getElementById('play-button'); 

    slider.max = timeKeys.length - 1;

    // 👇 Variables to manage the auto-play state
    let playbackInterval = null;
    const speed = 1000; // Milliseconds per step (adjust to speed up/slow down)

    slider.addEventListener('input', (e) => {
        const index = parseInt(e.target.value);
        const timestamp = timeKeys[index];
        
        // 1. Update Label (Human readable)
        // YYYY-MM-DD HH:mm, convert to local time Europe/Berlin
        const date = new Date(parseInt(timestamp));
        label.innerText = dateFormat(timestamp);

        const WeatherCode = meteoData.weatherMapper[timestamp].code;
        const IsDay = meteoData.weatherMapper[timestamp].is_day ? 'day' : 'night';
        const WeatherText = meteoDescriptions[WeatherCode][IsDay].description;
        const WeatherIcon = meteoDescriptions[WeatherCode][IsDay].image;

        // Update 
        needleGeoJSON.features.forEach(feature => {
            feature.properties.target_emission = feature.properties.ce_series[index];
            feature.properties.target_intensity = feature.properties.ci_series[index]; // Update target intensity as well
        });
        groundGeoJSON.features.forEach(feature => {
            feature.properties.target_intensity = feature.properties.ci_series[index];
        });

        // Fire up the animation loop if it isn't already running
        if (!isAnimating) {
            isAnimating = true;
            animateFrames();
        }

        datavalue.innerHTML = `
            <img class="weather-icon" src=${WeatherIcon}>  ${WeatherText}
        `;

        // 2. Update Map
        updateMapColors(timestamp);
        updateBaseMapStyle(timestamp);
        updateWeather(timestamp);
    });

    // 👇 --- AUTO PLAY LOGIC ---

    function togglePlayback() {
        if (playbackInterval) {
            pausePlayback();
        } else {
            playPlayback();
        }
    }

    function playPlayback() {
        playButton.textContent = 'Pause';
        
        playbackInterval = setInterval(() => {
            let currentIndex = parseInt(slider.value);
            let maxIndex = parseInt(slider.max);

            // Loop back to the beginning if we hit the end of timeKeys
            if (currentIndex >= maxIndex) {
                currentIndex = -1; // -1 because we add 1 immediately below
            }

            // Move to the next index step
            slider.value = currentIndex + 1;

            // Trigger the input event above to update Mapbox and UI text
            slider.dispatchEvent(new Event('input'));

        }, speed);
    }

    function pausePlayback() {
        clearInterval(playbackInterval);
        playbackInterval = null;
        playButton.textContent = 'Play';
    }

    // Event Listeners for Playback Controls
    if (playButton) {
        playButton.addEventListener('click', togglePlayback);
    }

    // Pause auto-play if the user manually grabs and drags the slider
    slider.addEventListener('mousedown', () => {
        if (playbackInterval) pausePlayback();
    });

    // 👆 --- END AUTO PLAY LOGIC ---

    // Trigger first frame
    slider.dispatchEvent(new Event('input'));
}


// function setupVisibilityToggle() {
//     const checkbox = document.getElementById('toggle-networks');
//     checkbox.addEventListener('change', (e) => {
//         const visibility = e.target.checked ? 'visible' : 'none';
//         const nodeVisibility = e.target.checked ? 'none' : 'visible';
//         map.setLayoutProperty('needle-layer', 'visibility', visibility);
//         map.setLayoutProperty('ground-layer', 'visibility', visibility);
//         map.setLayoutProperty('nodes-layer', 'visibility', nodeVisibility);
//     });
// }


function updateVisibility(checkbox) {
    const visibility = checkbox.checked ? 'visible' : 'none';
    const nodeVisibility = checkbox.checked ? 'none' : 'visible';
    
    // Wrap in style.load check or ensure map is loaded before calling
    if (map.isStyleLoaded()) {
        map.setLayoutProperty('needle-layer', 'visibility', visibility);
        map.setLayoutProperty('ground-layer', 'visibility', visibility);
        map.setLayoutProperty('nodes-layer', 'visibility', nodeVisibility);
    }
}

function setupVisibilityToggle() {
    const checkbox = document.getElementById('toggle-networks');

    // 2. Listen for future changes
    checkbox.addEventListener('change', () => updateVisibility(checkbox));
}


function animateFrames() {
    let changesMade = false;
    // add animation to needles
    needleGeoJSON.features.forEach(feature => {
        const current_ce = feature.properties.current_emission;
        const target_ce = feature.properties.target_emission;
        const diff_ce = target_ce - current_ce;

        const current_ci = feature.properties.current_intensity;
        const target_ci = feature.properties.target_intensity;
        const diff_ci = target_ci - current_ci;

        // If the current height hasn't reached the target yet
        if (Math.abs(diff_ce) > 0.05) {
            // Linear interpolation formula: current + (difference * speed)
            feature.properties.current_emission += diff_ce * ANIMATION_SPEED;
            feature.properties.current_intensity += diff_ci * ANIMATION_SPEED; // Update intensity in sync with height
            changesMade = true;
        } else {
            feature.properties.current_emission = target_ce; // Snap exactly to target
            feature.properties.current_intensity = target_ci; // Snap intensity to target as well
        }
    });

    // add animation to ground polygons
    groundGeoJSON.features.forEach(feature => {
        const current = feature.properties.current_intensity;
        const target = feature.properties.target_intensity;
        const diff = target - current;

        // If the current height hasn't reached the target yet
        if (Math.abs(diff) > 0.05) {
            // Linear interpolation formula: current + (difference * speed)
            feature.properties.current_intensity += diff * ANIMATION_SPEED;
            changesMade = true;
        } else {
            feature.properties.current_intensity = target; // Snap exactly to target
        }
    });

    if (changesMade) {
        // Update the map layer with the transitional heights
        map.getSource('needles').setData(needleGeoJSON);
        map.getSource('polygons').setData(groundGeoJSON);
        requestAnimationFrame(animateFrames);
    } else {
        isAnimating = false; // Stop the loop when all needles finish moving
    }
}


function updateMapColors(timestamp) {
    const stepData = nodeCIData[timestamp];
    
    // Efficiently update properties without rebuilding geometry
    for (const feature of nodeGeoData.features) {
        const nodeId = feature.properties.name;
        // Update intensity if it exists in current stepData
        if (stepData[nodeId] !== undefined) {
            feature.properties.current_intensity = stepData[nodeId];
        }
    }

    map.getSource('nodes').setData(nodeGeoData);

}

function updateBaseMapStyle(timestamp) {
    map.setConfigProperty('basemap', 'lightPreset', getLightPreset(timestamp, meteoData.weatherMapper[timestamp].sunrise, meteoData.weatherMapper[timestamp].sunset));
}


function updateWeather(timestamp) {


    const zoomBasedReveal = (value) => {
        return [
            'interpolate',
            ['linear'],
            ['zoom'],
            11,
            0.0,
            13,
            value
        ];
    };

    const weather = meteoData.weatherMapper[timestamp];

    const simulationDate = new Date(parseInt(timestamp));

    const sun = SunCalc.getPosition(
        simulationDate,
        initialCenter[1], // latitude
        initialCenter[0] // longitude
    );

    // radians -> degrees
    const azimuthDeg =
        (sun.azimuth * 180 / Math.PI) + 180;

    const altitudeDeg =   sun.altitude > 0.0 ? sun.altitude * 180 / Math.PI : 0.0 ;


    var intensity;

    if (weather.is_day === 1 && weather.is_rain ) {
        intensity = 0.2; // Dimmer during rain
    } else if (weather.is_day === 1 && weather.is_snow) {
        intensity = 0.3; // Slightly brighter during snow
    } else if (weather.is_day === 0) {
        intensity = 0.0; // Dim at night
    }
    else {
        intensity = 0.8;
    }

    map.setLights([
        {
            id: 'sun',
            type: 'directional',
            properties: {
                direction: [azimuthDeg, 90 - altitudeDeg],
                color: '#ffffff',
                intensity: intensity,
                'shadow-intensity': intensity
            }
        }
    ]);

    if (weather.is_rain) {
        map.setSnow(null);
        map.setRain({ 
            density: zoomBasedReveal(0.5),
            intensity: 1.0,
            color: '#a8adbc',
            opacity: 0.7,
            vignette: zoomBasedReveal(1.0),
            'vignette-color': '#464646',
            direction: [0, 80],
            'droplet-size': [2.6, 18.2],
            'distortion-strength': 0.7,
            'center-thinning': 0 // Rain to be displayed on the whole screen area

        });
    }
    else if (weather.is_snow) {
        map.setRain(null);
        map.setSnow({
            density: zoomBasedReveal(0.85),
            intensity: 1.0,
            'center-thinning': 0.1,
            direction: [0, 50],
            opacity: 1.0,
            color: `#ffffff`,
            'flake-size': 0.71,
            vignette: zoomBasedReveal(0.3),
            'vignette-color': `#ffffff`
        });
    }
    else {
        // Clear weather
        map.setRain(null);
        map.setSnow(null);
    }

}

function getColorFromValue(val) {
    if (val <= 10) return 'blue';
    else if (val <= 30) return 'green';
    else if (val <= 50) return 'orange';
    else if (val <= 70) return 'red';
    else if (val <= 90) return 'brown';
    else return 'black';
}


function dateFormat(timestamp) {
    const date = new Date(parseInt(timestamp));
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear().toString();
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}




loadMap();

