var RevealPointer=function(){
    "use strict";
    var e={backspace:8,tab:9,enter:13,shift:16,ctrl:17,alt:18,pausebreak:19,capslock:20,esc:27,space:32,pageup:33,pagedown:34,end:35,home:36,leftarrow:37,uparrow:38,rightarrow:39,downarrow:40,insert:45,delete:46,0:48,1:49,2:50,3:51,4:52,5:53,6:54,7:55,8:56,9:57,a:65,b:66,c:67,d:68,e:69,f:70,g:71,h:72,i:73,j:74,k:75,l:76,m:77,n:78,o:79,p:80,q:81,r:82,s:83,t:84,u:85,v:86,w:87,x:88,y:89,z:90,leftwindowkey:91,rightwindowkey:92,selectkey:93,numpad0:96,numpad1:97,numpad2:98,numpad3:99,numpad4:100,numpad5:101,numpad6:102,numpad7:103,numpad8:104,numpad9:105,multiply:106,add:107,subtract:109,decimalpoint:110,divide:111,f1:112,f2:113,f3:114,f4:115,f5:116,f6:117,f7:118,f8:119,f9:120,f10:121,f11:122,f12:123,numlock:144,scrolllock:145,semicolon:186,equalsign:187,comma:188,dash:189,period:190,forwardslash:191,graveaccent:192,openbracket:219,backslash:220,closebracket:221,singlequote:222};
    return function(){
        var t={},o=!1,a=null,n={x:0,y:0,isVisible:!1},i={x:0,y:0,scale:1};
        function l(o){
            var a;null==(t=o.pointer||{}).key?t.key="q":t.key=t.key.toLowerCase(),null!=t.pointerSize&&"number"==typeof t.pointerSize||(t.pointerSize=12),null!=t.tailLength&&"number"==typeof t.tailLength||(t.tailLength=10),null!=t.color&&"string"==typeof t.color||(t.color="red"),null!=t.alwaysVisible&&"boolean"==typeof t.alwaysVisible||(t.alwaysVisible=!1),t.keyCode=(a=t.key,e[a])
        }
        function s(){
            a.style.top="".concat((n.y-i.y)/i.scale,"px"),a.style.left="".concat((n.x-i.x)/i.scale,"px"),n.isVisible?a.style.opacity="0.8":a.style.opacity="0",1!==i.scale?(a.style.width="".concat(t.pointerSize/i.scale,"px"),a.style.height="".concat(t.pointerSize/i.scale,"px")):(a.style.width="".concat(t.pointerSize,"px"),a.style.height="".concat(t.pointerSize,"px"))
        }
        function c(e){
            n.x=e.pageX,n.y=e.pageY;var t=document.body.style.transform;""!==t?(i.x=Number.parseInt(/translate\((.*)px,/gm.exec(t)[1]),i.y=Number.parseInt(/px,\s(.*)px\)/gm.exec(t)[1]),i.scale=Number.parseFloat(/scale\((.)\)/gm.exec(t)[1])):(i.x=0,i.y=0,i.scale=1),requestAnimationFrame(s)
        }
        // function r(){
        //     (o=!o)?(document.addEventListener("mousemove",c),document.body.classList.add("no-cursor"),n.isVisible=!0):(document.removeEventListener("mousemove",c),document.body.classList.remove("no-cursor"),n.isVisible=!1,requestAnimationFrame(s))
        // } return{
        //     id:"pointer",init:function(e){var o;l(e.getConfig()),t.alwaysVisible?r():e.addKeyBinding({keyCode:t.keyCode,key:t.key},(function(){r()})),(o=document.createElement("div")).className="cursor-dot",o.style.width="".concat(t.pointerSize,"px"),o.style.height="".concat(t.pointerSize,"px"),o.style.backgroundColor=t.color,t.alwaysVisible&&(o.style.opacity="0.8"),document.body.appendChild(o),a=o}
        // }
        function hexToRgba(hex, alpha) {
        const bigint = parseInt(hex.slice(1), 16);
        const r = (bigint >> 16) & 255;
        const g = (bigint >> 8) & 255;
        const b = bigint & 255;
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

        function r() {
            (o = !o)
                ? (document.addEventListener("mousemove", c),
                document.body.classList.add("no-cursor"),
                n.isVisible = !0,
                requestAnimationFrame(s))
                : (document.removeEventListener("mousemove", c),
                document.body.classList.remove("no-cursor"),
                n.isVisible = !1);
        }

        return {
            id: "pointer",
            init: function (e) {
                var o;
                l(e.getConfig());
                t.alwaysVisible
                    ? r()
                    : e.addKeyBinding(
                        { keyCode: t.keyCode, key: t.key },
                        function () { r(); }
                    );

                // === Animated circle pointer setup ===
                const size = t.pointerSize || 40;
                const canvas = document.createElement("canvas");
                canvas.width = size;
                canvas.height = size;
                canvas.style.position = "fixed";
                canvas.style.pointerEvents = "none";
                canvas.style.zIndex = 9999;
                canvas.style.display = "none";
                document.body.appendChild(canvas);

                const ctx = canvas.getContext("2d");
                let isVisible = false;

                function render() {
                    if (!isVisible) return;
                    const duration = 1000;
                    const tAnim = (performance.now() % duration) / duration;
                    const radius = (size / 2) * 0.4;
                    const outerRadius = (size / 2) * 0.6 * tAnim + radius;

                    ctx.clearRect(0, 0, size, size);

                    // outer pulse
                    ctx.beginPath();
                    ctx.arc(size / 2, size / 2, outerRadius, 0, Math.PI * 2);
                    ctx.fillStyle = hexToRgba(t.color, 0.7 - tAnim*0.7) ;
                    ctx.fill();

                    // inner core
                    ctx.beginPath();
                    ctx.arc(size / 2, size / 2, radius, 0, Math.PI * 2);
                    ctx.fillStyle = hexToRgba(t.color, 0.7) ;
                    ctx.strokeStyle = hexToRgba('#ffffffed', 1.0) ;
                    ctx.lineWidth = 1 + 3 * (1 - tAnim);
                    ctx.fill();
                    ctx.stroke();

                    requestAnimationFrame(render);
                }

                function c(e) {
                    canvas.style.left = e.clientX - size / 2 + "px";
                    canvas.style.top = e.clientY - size / 2 + "px";
                }

                function s() {
                    if (isVisible) requestAnimationFrame(render);
                }

                function togglePointer() {
                    isVisible = !isVisible;
                    if (isVisible) {
                        document.body.classList.add("no-cursor");
                        canvas.style.display = "block";
                        document.addEventListener("mousemove", c);
                        requestAnimationFrame(render);
                    } else {
                        document.body.classList.remove("no-cursor");
                        canvas.style.display = "none";
                        document.removeEventListener("mousemove", c);
                    }
                }

                // === Replace original dot pointer ===
                a = canvas;
                n = { isVisible };
                o = false;

                // Assign toggle
                r = togglePointer;

                // Always visible mode
                if (t.alwaysVisible) togglePointer();
            }
        };


    }
}();
