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
    <div class="rows content-section" id="playlist display">
    </div>
</div>
""","settings" : """<div id="page-settings">
    This is the settings page
</div>
""",}