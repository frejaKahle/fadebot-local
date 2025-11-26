#populated by build process from files in \pages\
pages = {"discord" : """<div id="page-discord">
    This is the discord page
</div>
""","home" : """<div class="columns" id="page-home">
    <div class="rows">
        <div class="content-section columns" style="flex: 0 0;">
            <div class="form columns" id="queue_song">
                <input name="location" placeholder="Track Queue" required/>
                <button name="submit">Submit</button>
            </div>
            <div class="form columns" action="queue_playlist" id="queue_playlist">
                <select name="playlist_queue" id="playlist_queue" required>
                    <option value="" disabled selected hidden>Playlist Queue</option>
                </select>
                <button name="submit">Submit</button>
            </div>
        </div>
        <div class="content-section columns" id="now-playing"></div>
        <div class="content-section columns" style="flex: 0 0; justify-content: center;">
            <img class="icon" src="/assets/Pause.png" title="Pause" id="play_pause" disabled/>
            <img class="icon" src="/assets/Repeat_OFF.png" title="Repeating Off" id="repeat" data-repeat="0"/>
            <img class="icon" src="/assets/Skip.png" title="Skip" id="skip"/>
            <img class="icon" src="/assets/Skip_NF.png" title="Skip Without Fading" id="skip_nf"/>
            <img class="icon" src="/assets/Skip_Playlist.png" title="Skip Playlist" id="skip_playlist"/>
            <img class="icon" src="/assets/Skip_Playlist_NF.png" title="Skip Playlist Without Fading" id="skip_playlist_nf"/>
            <img class="icon" src="/assets/Rewind.png" title="Rewind" id="rewind"/>
            <img class="icon" src="/assets/Rewind_NF.png" title="Rewind Without Fading" id="rewind_nf"/>
            <div class="icorange columns" id="volume" title="Volume: 100%">
                <img src="/assets/Volume3.png"/>
                <input type="range" min="0.1" step="0.1" max="100.0" value="100.0"/>
            </div>
            <img class="icon" src="/assets/bug.png" title="debug" id="debug"/>
        </div>
    </div>   
    <div class="content-section" id="timeline"></div>
</div>
<script type="text/javascript" id="script-home">
    const repeat_map = {
         0: "Repeat_OFF", "Repeat_OFF": 0
        ,1: "Repeat_ONE", "Repeat_ONE": 1
        ,2: "Repeat_PLM", "Repeat_PLM": 2
        ,3: "Repeat_PLA", "Repeat_PLA": 3
        ,4: "Repeat_ALL", "Repeat_ALL": 4
        ,"titles":["Off", "One Track", "Playlist Main Sections", "Whole Playlists", "Whole Queue"]
    }
    const qs = document.getElementById("queue_song");
    const qp = document.getElementById("queue_playlist");
    qs.lastElementChild.onclick = function(e) {
        x = qs.children[0].value;
        qs.children[0].value = "";
        if (x == "") {return}
        console.log(`queueing song: ${x}`);
        eel.queue_song(x);
    };
    qp.lastElementChild.onclick = function(e) {
        x = qs.children[1].value;
        if (x == "") {return}
        console.log(`queueing playlist: ${x}`);
        eel.queue_playlist(x);
    };

    const pp = document.getElementById("play_pause");
    var playpause = true;
    pp.onclick = function() {
        if (playpause) {
            this.title = "Play";
            playpause = !playpause;
            this.src = "/assets/Play.png";
            eel.command("pause");
            console.log("Pausing");
        }
        else {
            this.title = "Pause";
            playpause = !playpause;
            this.src = "/assets/Pause.png"
            eel.command("resume");
            console.log("Playing");
        }
    };

    const r = document.getElementById("repeat");
    r.onclick = function() {
        i = (Number(this.dataset.repeat) + 1) % 5;
        this.src = `/assets/${repeat_map[i]}.png`;
        this.title = `Repeating ${repeat_map.titles[i]}`;
        this.dataset.repeat = i;
        console.log(this.dataset.repeat);
        eel.command(`repeat ${i}`);
        eel.aio_config({"repeat":i});
    };

    const v = document.getElementById("volume");
    v.lastElementChild.oninput = function() {
        volume = this.value;
        v.title = `Volume: ${volume}%`;
        v.firstElementChild.src = `/assets/Volume${Math.ceil((volume-0.19)/33.33)}.png`
        eel.command(`volume ${volume/100}`);
        eel.aio_config({"volume":Math.round(volume * 10)/1000});
    };

    const other_commands = ["skip","skip_nf","skip_playlist","skip_playlist_nf","rewind","rewind_nf"]
    other_commands.forEach(cmd => {
        document.getElementById(cmd).onclick = () => eel.command(cmd);
    });

    const debug = document.getElementById("debug").onclick = ((f) => {eel.debug()});

    eel.aio_config()().then(cfg => {
        
        r.dataset.repeat = cfg.repeat;
        r.src = `/assets/${repeat_map[cfg.repeat]}.png`;
        r.title = `Repeating ${repeat_map.titles[cfg.repeat]}`;

        v.title = `Volume: ${cfg.volume * 100}%`;
        v.lastElementChild.value = cfg.volume * 100;
    });

</script>""","playlists" : """<div class="columns" id="page-playlists">
    <div class="rows content-section" id="list-of-playlists">
        <button id="add-new-playlist">Add Playlist</button>
    </div>
    <div class="rows content-section" id="playlist-display"></div>
    <div id="add-new-playlist-popup" class="form rows">
        <input id="add-new-playlist-entry-name" placeholder="Playlist Name" required/>
        <input id="add-new-playlist-entry" placeholder="Playlist/Song URL"/>
        <button name="submit">Start Playlist</button>
    </div>
    <div id="add-new-playlist-popup-bg"></div>
</div>
<script type="text/javascript" id="script-playlists">
    const listOfPlaylists = document.getElementById("list-of-playlists");
    const listOfTracks = document.getElementById("playlist-display");
    const newPlaylistPopup = document.getElementById("add-new-playlist-popup");
    const newPlaylistPopupBG = document.getElementById("add-new-playlist-popup-bg");
    const newPlaylist = document.getElementById("add-new-playlist");
    const bufferIcon = document.getElementById("buffering_icon");
    let currentPlaylist = "";

    function openPopup() {
        newPlaylistPopup.classList.add("show");
        newPlaylistPopupBG.classList.add("show");
        newPlaylistPopup.children[0].value = "";
        newPlaylistPopup.children[1].value = "";
    }
    function closePopup() {
        newPlaylistPopup.classList.remove("show");
        newPlaylistPopupBG.classList.remove("show");
    }

    newPlaylist.onclick = openPopup;
    newPlaylistPopupBG.onclick = closePopup;
    newPlaylistPopup.lastElementChild.onclick = function() {
        bufferIcon.classList.add("show");
        var name =  newPlaylistPopup.children[0].value;
        var url = newPlaylistPopup.children[1].value;
        if (!name) return;
        if (url && url.length) 
        {
            eel.get_playlist_from_url(name, url)((result) => {
                bufferIcon.classList.remove("show");
                refreshPlaylists();
            });
            closePopup();
        }
    };

    function refreshPlaylists() {
        eel.get_playlists()(result => {
            while(listOfPlaylists.firstElementChild.tagName == "div")
            {
                listOfPlaylists.firstElementChild.remove();
            }
            Object.keys(result).forEach(key => {
                var entry = document.createElement("div");
                entry.id = `playlist-${key}`;
                entry.classList.add("playlist-entry", "columns");
                
                entry.appendChild(document.createElement("img"));
                entry.children[0].src = result[key]['image'];

                entry.appendChild(document.createElement("h1"));
                entry.children[1].innerHTML = key;

                entry.appendChild(document.createElement("button"));
                entry.children[2].classList.add("play");
                entry.children[2].onclick = () => {
                    eel.queue_playlist(result[key])();
                };

                entry.onclick = () => {
                    eel.get_playlists()(newResult => loadPlaylist(newResult[key]));
                    var element = listOfPlaylists.getElementsByClassName("active").item(0);
                    if (element) {
                        element.classList.remove("active");
                    }
                    entry.classList.add("active");
                };
                entry.oncontextmenu = () => {
                    entry.classList.toggle("contextMenu");
                    return false;
                };
                listOfPlaylists.insertBefore(entry,listOfPlaylists.lastElementChild);
                if (listOfPlaylists.firstElementChild == entry) {
                    entry.onclick();
                }
                //console.log(key, result[key]);
            });
        });
    }
    function loadPlaylist(playlist) {
        while(listOfTracks.firstChild) {
            listOfTracks.removeChild(listOfTracks.lastChild);
        }
        function createSectionHeader(name, key) {
            var header = document.createElement("div");
            header.classList.add("playlist-delimiter");
            header.appendChild(document.createElement("h1"));
            header.lastElementChild.innerHTML = name;
            header.appendChild(document.createElement("button"));
            header.lastElementChild.classList.add("plus");
            header.lastElementChild.onclick = () => {
                var newTrackEntry = document.createElement("div")
                newTrackEntry.classList.add("playlist-entry","setup","rows");
                newTrackEntry.appendChild(document.createElement("h2"));
                newTrackEntry.firstElementChild.innerHTML = "New Track";
                newTrackEntry.appendChild(document.createElement("div"));
                newTrackEntry.lastElementChild.classList.add("columns","form");
                newTrackEntry.lastElementChild.appendChild(document.createElement("input"));
                newTrackEntry.lastElementChild.lastElementChild.placeholder = "Track link";
                newTrackEntry.lastElementChild.appendChild(document.createElement("button"));
                newTrackEntry.lastElementChild.lastElementChild.classList.add("plus");
                newTrackEntry.lastElementChild.lastElementChild.onclick = () => {
                    var value = newTrackEntry.lastElementChild.firstElementChild.value;
                    if (value) {
                        bufferIcon.classList.add("show");
                        eel.get_track_from_url(value)(result => {
                            if (result.length > 0) {
                                var current = createSongDOM(result[0]);
                                newTrackEntry.replaceWith(current);
                                saveTrack(result[0], current);
                            }
                            if (result.length > 1) {
                                for(var i = 1; i < result.length; i++) {
                                    var prev = current;
                                    current = createSongDOM(result[i]);
                                    prev.insertAdjacentElement("afterend",current);
                                    saveTrack(result[i], current);
                                }
                            }});
                            bufferIcon.classList.remove("show");
                        }};
                

                var element = header.nextElementSibling;
                if (element && element.classList.contains("playlist-entry")) {
                    while (element.nextElementSibling && element.nextElementSibling.classList.contains("playlist-entry")){
                        element = element.nextElementSibling;
                    }
                    element.insertAdjacentElement("afterend",newTrackEntry);
                }
                else {
                    header.insertAdjacentElement("afterend",newTrackEntry);
                }
            };

            return header
        }
        
        listOfTracks.appendChild(createSectionHeader("Intro",'i'));
        if (playlist['i'].length > 0)
        {
            playlist['i'].forEach(track => {
                listOfTracks.appendChild(createSongDOM(track));
            });
        }
        listOfTracks.appendChild(createSectionHeader("Main",'m'));
        if (playlist['m'].length > 0)
        {
            playlist['m'].forEach(track => {
                listOfTracks.appendChild(createSongDOM(track));
            });
        }
        listOfTracks.appendChild(createSectionHeader("Outro",'o'));
        if (playlist['o'].length > 0)
        {
            playlist['o'].forEach(track => {
                listOfTracks.appendChild(createSongDOM(track));
            });
        }
    }
    function createSongDOM(track) {
        var entry = document.createElement("div");
        entry.classList.add("playlist-entry","columns");
        
        entry.appendChild(document.createElement("img"));
        entry.children[0].src = track['image'];
        
        
        entry.appendChild(document.createElement("div"));
        entry.children[1].classList.add("rows");
        entry.children[1].appendChild(document.createElement("h2"));
        
        entry.children[1].children[0].innerHTML = track['name'];

        entry.appendChild(document.createElement("button"));
        entry.children[2].classList.add("play");
        entry.children[2].onclick = () => {
            console.log(track);
            eel.queue_preloaded_song(track)( result => saveTrack(result, entry));
        }

        var artist = track['artist'];
        if (artist) {
            entry.children[1].appendChild(document.createElement("h3"));
            entry.children[1].children[1].innerHTML = artist;
        }
        return entry;
    }

    function saveTrack(track, entry) {
        var playlistKey = document.getElementsByClassName("playlist-entry active").item(0).id.substring(9);
        var prevSibling = entry.previousElementSibling;
        var i = 0;
        while(!prevSibling.classList.contains("playlist-delimiter")) {
            prevSibling = prevSibling.previousElementSibling;
            i++;
        }
        var sectionKey = prevSibling.firstElementChild.innerHTML.substring(0,1).toLowerCase();
        eel.save_track(playlistKey,sectionKey,i,track);
    }
    refreshPlaylists();  
</script>""","settings" : """<div id="page-settings">
    This is the settings page
</div>
""",}