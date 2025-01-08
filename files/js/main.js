document.getElementById("nav-home").addEventListener("click", ()=>{eel.switch_page("home")}, false);
document.getElementById("nav-playlists").addEventListener("click", ()=>{eel.switch_page("playlists")}, false);
document.getElementById("nav-discord").addEventListener("click", ()=>{eel.switch_page("discord")}, false);
document.getElementById("nav-settings").addEventListener("click", ()=>{eel.switch_page("settings")}, false);

eel.expose(change_content);
function change_content(html) {
    content_div = document.getElementById("main_content");
    while (content_div.firstChild) {
        content_div.removeChild(content_div.lastChild);
      }
    content_div.innerHTML = html;
    scripts = document.querySelectorAll("script");
    if (scripts.length > 2) {
        text = scripts[scripts.length - 2].textContent;
        var newScript = document.createElement("script");
        newScript.textContent = text;
        content_div.appendChild(newScript);
    }
}

eel.expose(switch_active_nav);
function switch_active_nav(prev_tab, next_tab) {
    document.getElementById(prev_tab).classList.remove("active");
    document.getElementById(next_tab).classList.add("active");
}

eel.switch_page("home");
