function updateLogoSizePosition(event) {
    if (event.currentSlide.matches('#title-slide') || event.currentSlide.matches('.unnumbered')) {
    var elements = document.querySelectorAll(".slide-logo");
    [].forEach.call(elements, function(elem) {
        elem.classList.remove("slide-logo-normal");
        elem.classList.add("slide-logo-max-size");
    });
    } else {
    var elements = document.querySelectorAll(".slide-logo");
    [].forEach.call(elements, function(elem) {
        elem.classList.add("slide-logo-normal");
        elem.classList.remove("slide-logo-max-size");
    });
    }
};

function updateFooterShow(event) {
    if (event.currentSlide.matches('#title-slide') || event.currentSlide.matches('.unnumbered')) {
    var elements = document.querySelectorAll(".reveal .footer, .reveal .slide-number, .reveal .slide-menu-button, .reveal .slide-chalkboard-buttons");
    [].forEach.call(elements, function(elem) {
        elem.style.display = "none";
    });
    } else {
    var elements = document.querySelectorAll(".reveal .footer, .reveal .slide-number, .reveal .slide-menu-button, .reveal .slide-chalkboard-buttons");
    [].forEach.call(elements, function(elem) {
        elem.style.display = "block";
    });
    }
}

window.addEventListener("load", (event) => {
    var elements = document.querySelectorAll(".slide-logo");
    [].forEach.call(elements, function(elem) {
    elem.classList.remove("slide-logo-normal");
    elem.classList.add("slide-logo-max-size");
    });
    var footerElements = document.querySelectorAll(".reveal .footer, .reveal .slide-number, .reveal .slide-menu-button, .reveal .slide-chalkboard-buttons");
    [].forEach.call(footerElements, function(elem) {
    elem.style.display = "none";
    });

    Reveal.on("slidechanged", function(event) {
    updateLogoSizePosition(event);
    updateFooterShow(event);
    });

    Reveal.on("ready", function(event) {
    updateLogoSizePosition(event);
    updateFooterShow(event);
    });
    
    Reveal.on("resize", function(event) {
    updateLogoSizePosition({ currentSlide: Reveal.getCurrentSlide() });
    updateFooterShow({ currentSlide: Reveal.getCurrentSlide() });
    });

});

// A single structural function to handle your state on any event
// function syncSlideLayout(currentSlide) {
//     var logos = document.querySelectorAll(".slide-logo");
//     var uiElements = document.querySelectorAll(
//         ".reveal .footer, .reveal .slide-number, .reveal .slide-menu-button, .reveal .slide-chalkboard-buttons"
//     );

//     // Safety check if slide hasn't loaded yet
//     if (!currentSlide) return;

//     if (currentSlide.matches('#title-slide') || currentSlide.matches('.unnumbered')) {
//         // 1. Title Slide State
//         [].forEach.call(logos, function(elem) {
//             elem.classList.remove("slide-logo-normal");
//             elem.classList.add("slide-logo-max-size");
//         });
//         [].forEach.call(uiElements, function(elem) {
//             elem.style.setProperty("display", "none", "important");
//         });
//     } else {
//         // 2. Standard Content Slide State
//         [].forEach.call(logos, function(elem) {
//             elem.classList.add("slide-logo-normal");
//             elem.classList.remove("slide-logo-max-size");
//         });
//         [].forEach.call(uiElements, function(elem) {
//             // Restore default view (Reveal.js uses flex or block natively depending on the asset)
//             elem.style.removeProperty("display"); 
//         });
        
//         // If your custom functions handle deeper logic, run them safely here:
//         if (typeof updateLogoSizePosition === "function") updateLogoSizePosition({ currentSlide: currentSlide });
//         if (typeof updateFooterShow === "function") updateFooterShow({ currentSlide: currentSlide });
//     }
// }

// // Global Event Registration
// if (typeof Reveal !== 'undefined') {
//     // RUN ONCE REVEAL IS FULLY INITIALIZED AND RESCALED
//     Reveal.on("ready", function(event) {
//         syncSlideLayout(event.currentSlide);
//     });

//     // RUN ON EVERY SLIDE CHANGE
//     Reveal.on("slidechanged", function(event) {
//         syncSlideLayout(event.currentSlide);
//     });

//     // RUN ON RESIZE (Fixes layout breaks when maximizing/minimizing window)
//     Reveal.on("resize", function(event) {
//         syncSlideLayout(Reveal.getCurrentSlide());
//     });
// } else {
//     // Fallback if Reveal isn't fully ready in the global namespace yet
//     window.addEventListener("load", () => {
//         if (typeof Reveal !== 'undefined' && Reveal.isReady()) {
//             syncSlideLayout(Reveal.getCurrentSlide());
//         }
//     });
// }
