function syncSlideLayout(currentSlide) {
    var logos = document.querySelectorAll(".slide-logo");
    var uiElements = document.querySelectorAll(
        ".reveal .footer, .reveal .slide-number, .reveal .slide-menu-button, .reveal .slide-chalkboard-buttons"
    );
    var liveLink = document.querySelectorAll("#live-link");

    // Safety check if slide hasn't loaded yet
    if (!currentSlide) return;

    if (currentSlide.matches('#title-slide') || currentSlide.matches('#thanks-slide')) {
        // 1. Title Slide State
        [].forEach.call(logos, function(elem) {
            elem.classList.remove("slide-logo-normal");
            elem.classList.add("slide-logo-max-size");
        });
        [].forEach.call(uiElements, function(elem) {
            elem.style.setProperty("display", "none", "important");
        });
        [].forEach.call(liveLink, function(elem) {
            elem.style.setProperty("display", "none", "important");
        });
    } else {
        // 2. Standard Content Slide State
        [].forEach.call(logos, function(elem) {
            elem.classList.add("slide-logo-normal");
            elem.classList.remove("slide-logo-max-size");
        });
        [].forEach.call(uiElements, function(elem) {
            // Restore default view (Reveal.js uses flex or block natively depending on the asset)
            elem.style.removeProperty("display"); 
        });
        [].forEach.call(liveLink, function(elem) {
            elem.style.removeProperty("display"); 
        });
        
        // If your custom functions handle deeper logic, run them safely here:
        if (typeof updateLogoSizePosition === "function") updateLogoSizePosition({ currentSlide: currentSlide });
        if (typeof updateFooterShow === "function") updateFooterShow({ currentSlide: currentSlide });
    }
}


window.addEventListener("load", (event) => {
    // Global Event Registration
    if (typeof Reveal !== 'undefined') {
        // RUN ONCE REVEAL IS FULLY INITIALIZED AND RESCALED
        // console.log("Reveal detected. Registering event listeners for slide layout sync.");
        syncSlideLayout(Reveal.getCurrentSlide());
        // console.log("Reveal is ready. Initial slide layout synced.");

        // RUN ON EVERY SLIDE CHANGE
        Reveal.on("slidechanged", function(event) {
            syncSlideLayout(Reveal.getCurrentSlide());
            // console.log("Slide changed. Current slide layout synced.");
        });

        // RUN ON RESIZE (Fixes layout breaks when maximizing/minimizing window)
        Reveal.on("resize", function(event) {
            syncSlideLayout(Reveal.getCurrentSlide());
            // console.log("Window resized. Current slide layout synced.");
        });
    } else {
        // Fallback if Reveal isn't fully ready in the global namespace yet
        console.warn("Reveal not detected on load. Will attempt to sync layout on window load.");
    }
});