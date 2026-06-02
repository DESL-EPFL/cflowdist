function renderPlotly(divId, jsonPath) {

  const plotlyConfig = {
            // Standard config options (e.g., responsiveness)
            responsive: true,
            
            // --- Custom Mode Bar Logic ---
            modeBarButtonsToRemove: ['toImage'],
            modeBarButtonsToAdd: [{
                name: 'toSVGImage',
                title: 'Download plot as SVG', // Add a helpful tooltip
                icon: Plotly.Icons.camera,
                click: function(gd) {
                    // This function is executed when the button is clicked
                    Plotly.downloadImage(gd, { format: 'svg', filename: 'plotly-svg' });
                }
            }]
        };
  // Use the built-in Plotly.js to fetch the JSON data
  fetch(jsonPath)
    .then(response => response.json())
    .then(figure => {
      // Use Plotly.newPlot to render the figure into the specified div

      if (figure.layout.font) {

        const para = document.querySelector("p");
        const computedFontFamily = window.getComputedStyle(para).getPropertyValue("font-family")
        figure.layout.font.family = computedFontFamily;
      }
      Plotly.newPlot(
        document.getElementById(divId), 
        figure.data, 
        figure.layout,
        plotlyConfig
      );
    })
    .catch(error => {
      console.error("Error fetching or plotting JSON:", error);
    });
}