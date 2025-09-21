const pages = ["home","playlists","discord","settings"];
const content_div = document.getElementById("main_content");
let current_page = pages[0];
let np;

function page_dom(pagename) {
    return document.getElementById(`page-${pagename}`);
}
function nav_dom(pagename) {
    return document.getElementById(`nav-${pagename}`);
}

eel.expose(switch_page);
function switch_page(pagename) {
    if (pagename != current_page) {
        page_dom(current_page).classList.add("hidden");
        page_dom(pagename) .classList.remove("hidden");

        nav_dom(pagename).classList.add("active");
        nav_dom(current_page).classList.remove("active");
        
        current_page = pagename;   
    }
}


const parser = new DOMParser();
async function setup_pages() {
    // Load all the pages and their scripts
    await Promise.all(pages.map(async (pagename) => {
        nav_dom(pagename).addEventListener("click", () => {switch_page(pagename)}, false);
        content = await eel.get_page(pagename)();

        parser.parseFromString(content, 'text/html').lastElementChild.lastElementChild.childNodes.forEach(node => {
            if (node.tagName == 'SCRIPT') {
                var s = document.createElement('script');
                s.textContent = node.textContent;
                document.body.appendChild(s);
            }
            else content_div.appendChild(node);
        });
        //var script = document.getElementById(`script-${pagename}`);
        //if (script) {
        //    var newScript = document.createElement("script");
        //    newScript.textContent = script.textContent;
        //    document.head.appendChild(newScript);
        //}
        if (pagename != current_page) page_dom(pagename).classList.add("hidden");
    }));

    // After the all html has loaded:
    np = document.getElementById("now-playing");
}

function swap_CaR(element) {
    if (element.classList.contains("column")) element.classList.replace("column","row");
    else element.classList.replace("row","column");
}

function update_responsive_flex_containers() {
    let collection = document.getElementsByClassName("resp-CaR");
    let elem;
    for (let i = 0;i < collection.length; i++) {
        elem = collection.item(i);
        swap_CaR(elem);
    }
}

eel.expose(nowPlaying);
function nowPlaying(songs) {
    if(!np) return;
    np.innerHTML = "";
    if (songs) songs.forEach(song => {
        var container = document.createElement('div');
        container.className = "rows";

        var img = document.createElement("img");
        img.setAttribute('src',song.img);
        container.appendChild(img);

        var title = document.createElement("h3");
        title.innerHTML = song.name;
        if (song.album) title.innerHTML += ` - ${song.album}`;
        container.appendChild(title);

        var artist = document.createElement("h4");
        artist.innerHTML = `by ${song.artist}`;
        container.appendChild(artist);

        np.appendChild(container);
    });
}

setup_pages();
