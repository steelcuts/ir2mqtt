import io
import logging
import re
import tempfile
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

logger = logging.getLogger("ir2mqtt")

SUPPORTED_PROTOCOLS = {
    "nec",
    "samsung",
    "samsung36",
    "sony",
    "panasonic",
    "rc5",
    "rc6",
    "jvc",
    "lg",
    "coolix",
    "pioneer",
    "dish",
    "midea",
    "haier",
    "pronto",
    "raw",
    # New protocols
    "aeha",
    "abbwelcome",
    "beo4",
    "byronsx",
    "canalsat",
    "canalsat_ld",
    "dooya",
    "drayton",
    "dyson",
    "gobox",
    "keeloq",
    "magiquest",
    "mirage",
    "nexa",
    "rc_switch",
    "roomba",
    "symphony",
    "toshiba_ac",
    "toto",
    # Legacy
    # "whynter", "sharp", "sanyo", "toshiba", "rca",
}


def parse_flipper_hex(hex_str: str) -> str:
    """
    Converts Flipper Little Endian hex string (e.g. '04 00 00 00')
    to a standard hex string (e.g. '0x4').
    """
    try:
        # Remove spaces, convert to bytes, interpret as Little Endian
        clean_hex = hex_str.replace(" ", "")
        # Pad with 0 if odd length (just in case)
        if len(clean_hex) % 2 != 0:
            clean_hex = "0" + clean_hex

        val = int.from_bytes(bytes.fromhex(clean_hex), byteorder="little")
        return f"0x{val:X}"
    except Exception:
        # Fallback if parsing fails
        return hex_str


def flipper_hex_to_int(hex_str: str) -> int:
    try:
        clean_hex = hex_str.replace(" ", "")
        if len(clean_hex) % 2 != 0:
            clean_hex = "0" + clean_hex
        return int.from_bytes(bytes.fromhex(clean_hex), byteorder="little")
    except Exception:
        return 0


def standardize_ir_key(raw_name: str) -> dict[str, str]:
    """
    Analyzes a raw IR button name and returns a standardized name
    and a matching MDI icon.
    Optimized for specific missing icons (Slow, Arrows, Disc, Climate).
    """
    if not raw_name:
        return {"name": "Unknown", "icon": "remote", "category": "Other"}

    # 1. Pre-cleaning & De-Spacing
    n = raw_name.strip()

    # "Wide Char" Detector (e.g. "K E Y")
    if len(n) > 3 and re.match(r"^([A-Za-z0-9+-]\s)+[A-Za-z0-9+-]$", n):
        n = n.replace(" ", "")

    n = n.lower()

    # Remove technical prefixes
    n = re.sub(r"^(key|btn|ir|cmd|k_e_y)_?", "", n)

    # Clean up trailing special characters
    n = re.sub(r"(\[\]|\(\))$", "", n)

    # 2. Specific symbol replacement BEFORE pattern matching
    # Converts "Volume V" or "Down V" into readable text
    if n.endswith(" v"):
        n = n[:-2] + " down"
    if n.endswith(" ^"):
        n = n[:-2] + " up"

    # --- Fallback Name Generation ---
    fallback_name = n
    fallback_name = re.sub(r"[_\.]", " ", fallback_name)
    # Make symbols in name readable
    fallback_name = fallback_name.replace("^", " Up").replace(">>", " Fwd").replace("<<", " Rev").replace(">", " Fwd").replace("<", " Rev")
    # Split CamelCase
    fallback_name = re.sub(r"(?<!^)(?=[A-Z])", " ", fallback_name)
    # Title Case
    fallback_name = " ".join([w.capitalize() for w in fallback_name.split()]).strip()

    if len(fallback_name) > 20:
        fallback_name = fallback_name[:20]

    result = {"name": fallback_name, "icon": "remote", "category": "Other"}

    # 3. Pattern Matching
    patterns = [
        # --- POWER ---
        (r"^(power|pwr|tv.*power).*(on|true|assert)$", "Power On", "power-on", "Power"),
        (
            r"^(power|pwr|tv.*power).*(off|false|assert)$",
            "Power Off",
            "power-off",
            "Power",
        ),
        (
            r"^(power|pwr|on/off|on.*off|power.*toggle|tv.*power)$",
            "Power",
            "power",
            "Power",
        ),
        (r"^(on)$", "Power On", "power-on", "Power"),
        (r"^(off)$", "Power Off", "power-off", "Power"),
        (r"^standby$", "Standby", "power-sleep", "Power"),
        # --- AUDIO ---
        (
            r"^(vol|volume|vol\.).*(up|\+|inc|plus|\^)$",
            "Vol Up",
            "volume-plus",
            "Audio",
        ),
        (
            r"^(vol|volume|vol\.).*(dn|down|\-|dec|v|dwn)$",
            "Vol Down",
            "volume-minus",
            "Audio",
        ),
        (r"^(bass).*(up|\+|inc|plus)$", "Bass Up", "music-note-plus", "Audio"),
        (r"^(bass).*(dn|down|\-|dec)$", "Bass Down", "music-note-minus", "Audio"),
        (r"^(treble).*(up|\+|inc|plus)$", "Treble +", "equalizer", "Audio"),
        (r"^(treble).*(dn|down|\-|dec)$", "Treble -", "equalizer", "Audio"),
        (
            r"^(mute|mute.*toggle|muting|mute.*on|mute.*off)$",
            "Mute",
            "volume-mute",
            "Audio",
        ),
        (r"^(audio|sound|audio.*mode|mts|sap)$", "Audio", "volume-high", "Audio"),
        (r"^(surround|stereo|thx|mono|mix)$", "Surround", "surround-sound", "Audio"),
        (r"^(eq|equalizer|bass|treble|tone)$", "EQ", "equalizer", "Audio"),
        (r"^(fader|bal|balance)$", "Balance", "scale-balance", "Audio"),
        # --- TUNER / CHANNEL ---
        (
            r"^(ch|chan|prog|pre-ch).*(up|\+|inc|next|fwd|10channelsup)$",
            "Ch Up",
            "television-shimmer",
            "Tuner",
        ),
        (
            r"^(ch|chan|prog|pre-ch).*(dn|down|\-|dec|prev)$",
            "Ch Down",
            "television-shimmer",
            "Tuner",
        ),
        (r"^(preset).*(up|\+|inc)$", "Preset +", "view-list", "Tuner"),
        (r"^(preset).*(dn|down|\-|dec)$", "Preset -", "view-list", "Tuner"),
        (r"^(ch|chan).*(list|guide)$", "Ch List", "format-list-bulleted", "Tuner"),
        (r"^(prev|last).*ch$", "Last Ch", "history", "Tuner"),
        (r"^(last|recall|jump|call)$", "Last Ch", "history", "Tuner"),
        (r"^(list|listing)$", "List", "format-list-bulleted", "Tuner"),
        (
            r"^(scan|seek|seek/scan).*(up|\+|inc|fwd|>>)$",
            "Scan +",
            "radio-tower",
            "Tuner",
        ),
        (
            r"^(scan|seek|seek/scan).*(dn|down|\-|dec|rev|<<)$",
            "Scan -",
            "radio-tower",
            "Tuner",
        ),
        (r"^(scan)$", "Scan", "radio-tower", "Tuner"),
        (r"^(tune).*(up|\+|inc|fwd|>>)$", "Tune +", "radio-tower", "Tuner"),
        (r"^(tune).*(dn|down|\-|dec|rev|<<)$", "Tune -", "radio-tower", "Tuner"),
        (
            r"^(band|fm.*am.*toggle|am/fm|fm|am|radio|tuner|tv/radio|fm.*assert|am.*assert)$",
            "Radio",
            "radio",
            "Tuner",
        ),
        # --- NAVIGATION ---
        (r"^(up|arrow.*up|cursor.*up|menu.*up)$", "Up", "chevron-up", "Nav"),
        (
            r"^(down|arrow.*down|cursor.*down|menu.*down)$",
            "Down",
            "chevron-down",
            "Nav",
        ),
        (
            r"^(left|arrow.*left|cursor.*left|left.*arrow|menu.*left)$",
            "Left",
            "chevron-left",
            "Nav",
        ),
        (
            r"^(right|arrow.*right|cursor.*right|menu.*right)$",
            "Right",
            "chevron-right",
            "Nav",
        ),
        (
            r"^(ok|enter|select|confirm|sel|cursor.*enter|set|check|ent)$",
            "OK",
            "check-circle-outline",
            "Nav",
        ),
        (r"^(back|return|cancel|exit|esc)$", "Back", "arrow-left-circle", "Nav"),
        (
            r"^(menu|home|options|option[s]?|dvd.*menu|top.*menu)$",
            "Menu",
            "menu",
            "Nav",
        ),
        (
            r"^(info|display|guide|epg|i|status|osd|on.*screen|view|disp)$",
            "Info",
            "information-outline",
            "Nav",
        ),
        (r"^(tools|settings|setup|system|opt|function)$", "Setup", "cog", "Nav"),
        (r"^(page|pg|pageup).*(up|\+|inc|plus)$", "Page Up", "arrow-up-bold", "Nav"),
        (
            r"^(page|pg|pagedown).*(dn|down|\-|dec)$",
            "Page Down",
            "arrow-down-bold",
            "Nav",
        ),
        (r"^(clear|cls|delete|del)$", "Clear", "backspace-outline", "Nav"),
        (r"^(search|find).*(<<|rev|prev)$", "Search -", "magnify-minus", "Nav"),
        (r"^(search|find).*(>>|fwd|next)$", "Search +", "magnify-plus", "Nav"),
        (r"^(search|find)$", "Search", "magnify", "Nav"),
        (r"^(goto)$", "Goto", "arrow-right-bold", "Nav"),
        (r"^(index)$", "Index", "format-list-numbered", "Nav"),
        # --- MEDIA ---
        (
            r"^(play[ \/\-_]?pause|p[ \/\-_]?p|pause.*toggle)$",
            "Play/Pause",
            "play-pause",
            "Media",
        ),
        (r"^(play|start|play.*>|cd.*play|resume)$", "Play", "play", "Media"),
        (r"^(pause|freeze|still|cd.*pause|pause/still)$", "Pause", "pause", "Media"),
        (r"^(stop|.*stop)$", "Stop", "stop", "Media"),  # Catches Cd Stop, Tape Stop
        (
            r"^(rew|rewind|scan.*rev|<<|fast.*ba|rev|reverse|skip.*back|rew.*rev)$",
            "Rewind",
            "rewind",
            "Media",
        ),
        (
            r"^(ff|fwd|fast.*fwd|>>|forward|fast.*fo|fast.*forward|skip.*forward|ff.*fwd)$",
            "Fast Fwd",
            "fast-forward",
            "Media",
        ),
        (r"^(rec|record)$", "Record", "record", "Media"),
        (
            r"^(next|skip.*fwd|>>\||skip.*>>|skip|cd.*skip.*fwd|disc.*skip)$",
            "Next",
            "skip-next",
            "Media",
        ),
        (
            r"^(prev|previous|skip.*rev|\|<<|skip.*<<|cd.*skip.*rev)$",
            "Prev",
            "skip-previous",
            "Media",
        ),
        (r"^(eject|open.*close|open|close|ejectcd)$", "Eject", "eject", "Media"),
        # --- MEDIA EXTRAS (Disc, Slow, Repeat) ---
        (r"^(subtitle|subs|cc|caption|txt)$", "Subtitle", "subtitles", "Media"),
        (
            r"^(repeat|again|loop|replay)$",
            "Repeat",
            "repeat",
            "Media",
        ),  # Replay handled here
        (r"^(random|shuffle)$", "Shuffle", "shuffle", "Media"),
        (r"^(slow.*(\-|down|rev)|frame.*rev)$", "Slow -", "speedometer-slow", "Media"),
        (
            r"^(slow.*(\+|up|fwd)|slow|slow.*motion|step|frame.*fwd)$",
            "Slow +",
            "speedometer-slow",
            "Media",
        ),
        (r"^(angle)$", "Angle", "camera-control", "Media"),
        (r"^(title)$", "Title", "format-title", "Media"),
        (r"^(pip)$", "PIP", "picture-in-picture-bottom-right", "Media"),
        (
            r"^(aspect|ratio|zoom|wide|format|p.*size|size)$",
            "Aspect",
            "aspect-ratio",
            "Media",
        ),
        (r"^(text)$", "Text", "text-box-outline", "Media"),
        (r"^(a[\-]b|repeat.*a.*b|ab|marker)$", "A-B", "repeat-once", "Media"),
        (r"^(picture|pic|p.*mode)$", "Picture", "image", "Media"),
        (r"^(music|umusic|s.*mode)$", "Sound Mode", "music", "Media"),
        (r"^(language|lang)$", "Language", "translate", "Media"),
        (r"^(intro)$", "Intro", "presentation-play", "Media"),
        (r"^(pbc)$", "PBC", "disc-player", "Media"),
        (r"^(playlist)$", "Playlist", "playlist-play", "Media"),
        (r"^(3d)$", "3D", "video-3d", "Media"),
        (r"^(movie)$", "Movie", "movie", "Media"),
        (r"^(game)$", "Game", "gamepad-variant", "Media"),
        (r"^(disc|cd)\s*([0-9])$", lambda m: f"Disc {m.group(2)}", "album", "Media"),
        (r"^(disc.*(\+|up))$", "Disc +", "album", "Media"),
        (r"^(disc.*(\-|down))$", "Disc -", "album", "Media"),
        (r"^(disc|cd|dvd|whole.*cd)$", "Disc", "disc", "Media"),
        (r"^(continue)$", "Continue", "play-box-outline", "Media"),
        (r"^(blank)$", "Blank", "crop-landscape", "Media"),
        # --- CLIMATE ---
        (
            r"^(temp|temperature).*(up|\+|inc|plus|high)$",
            "Temp Up",
            "thermometer-plus",
            "Climate",
        ),
        (
            r"^(temp|temperature).*(dn|down|\-|dec|low)$",
            "Temp Down",
            "thermometer-minus",
            "Climate",
        ),
        (r"^(fan|speed|fan.*speed)$", "Fan Speed", "fan", "Climate"),
        (r"^(cool)$", "Cool", "snowflake", "Climate"),
        (r"^(heat|warm)$", "Heat", "fire", "Climate"),
        (r"^(swing|oscillate|osc)$", "Swing", "arrow-oscillating", "Climate"),
        # --- INPUTS ---
        (
            r"^(input|source|src|in.*[0-9]|tv.*input|local.*source)$",
            "Source",
            "import",
            "Input",
        ),
        (
            r"^hdmi.*([0-9]+)$",
            lambda m: f"HDMI {m.group(1)}",
            "video-input-hdmi",
            "Input",
        ),
        (r"^hdmi$", "HDMI", "video-input-hdmi", "Input"),
        (
            r"^(av|aux|video.*|tv.*video|tv.*vcr)$",
            "AV/Aux",
            "video-input-component",
            "Input",
        ),
        (r"^(tv)$", "TV", "television", "Input"),
        (r"^(tape|cassette|tape.*[1-2])$", "Tape", "cassette", "Input"),
        (r"^(phono)$", "Phono", "record-player", "Input"),
        (r"^(vcr|vcr.*1|vcr.*2)$", "VCR", "video-vintage", "Input"),
        (r"^(usb)$", "USB", "usb", "Input"),
        (r"^(bluetooth|bt)$", "Bluetooth", "bluetooth", "Input"),
        (r"^(sat|satellite|cbl.*sat)$", "Sat", "satellite-uplink", "Input"),
        (r"^(pc|computer)$", "PC", "desktop-tower", "Input"),
        (r"^(optical|opt)$", "Optical", "expansion-card", "Input"),
        (r"^(s-video|s-v)$", "S-Video", "video-input-svideo", "Input"),
        (r"^(ld|laserdisc)$", "LaserDisc", "disc", "Input"),
        (r"^(netflix)$", "Netflix", "netflix", "Input"),
        (r"^(youtube)$", "YouTube", "youtube", "Input"),
        (r"^(prime.*video|amazon)$", "Prime", "amazon", "Input"),
        (r"^(apps)$", "Apps", "apps", "Input"),
        # --- PICTURE / DISPLAY ---
        (r"^(bright.*up)$", "Bright +", "brightness-7", "Other"),
        (r"^(bright.*down)$", "Bright -", "brightness-5", "Other"),
        (r"^(bright|brightness)$", "Brightness", "brightness-6", "Other"),
        (r"^(contrast)$", "Contrast", "contrast-circle", "Other"),
        (r"^(dimmer|dim)$", "Dimmer", "brightness-4", "Other"),
        # --- COLOR ---
        (r"^(red|r|pink)$", "Red", "button-cursor", "Color"),
        (r"^(green|g)$", "Green", "button-cursor", "Color"),
        (
            r"^(blue|b|purple)$",
            "Blue",
            "button-cursor",
            "Color",
        ),  # Purple often grouped with Blue
        (r"^(yellow|y)$", "Yellow", "button-cursor", "Color"),
        (r"^white$", "White", "palette-swatch-outline", "Color"),
        (r"^orange$", "Orange", "palette", "Color"),
        # --- DIGITS ---
        (
            r"^([0-9])$",
            lambda m: m.group(1),
            lambda m: f"numeric-{m.group(1)}-box",
            "Digit",
        ),
        (
            r"^(1[0-2])$",
            lambda m: m.group(1),
            lambda m: f"numeric-{m.group(1)}-box-multiple-outline",
            "Digit",
        ),  # 10, 11, 12
        (r"^(100)$", "100", "numeric-10-box-multiple-outline", "Digit"),
        (
            r"^(>10|10\+|10channelsup|0\+|x.*key.*0\+|102nd|fwd10)$",
            "10+",
            "numeric-10-box-multiple-outline",
            "Digit",
        ),
        (
            r"^([a-e]|i|m|t|w)$",
            lambda m: m.group(1).upper(),
            lambda m: f"alpha-{m.group(1)}-box",
            "Digit",
        ),
        (r"^(kp.*plus|kpplus)$", "Keypad +", "plus-box", "Digit"),
        (r"^(kp.*minus|kpminus)$", "Keypad -", "minus-box", "Digit"),
        (r"^(\*)$", "*", "asterisk", "Digit"),
        (r"^(#)$", "#", "pound", "Digit"),
        (r"^(dot)$", ".", "record", "Digit"),
        # --- F-KEYS ---
        (
            r"^f\s*([0-9]{1,2})$",
            lambda m: f"F{m.group(1)}",
            lambda m: f"keyboard-f{m.group(1)}",
            "Other",
        ),
        # --- OTHER ---
        (r"^(timer|sleep|delay)$", "Timer", "timer-sand", "Other"),
        (r"^(mode)$", "Mode", "tune", "Other"),
        (r"^(time|clock)$", "Time", "clock-outline", "Other"),
        (r"^(fav|favorite[s]?)$", "Fav", "star", "Other"),
        (r"^(light|lamp)$", "Light", "lightbulb", "Other"),
        (r"^(flash|strobe)$", "Flash", "flash", "Other"),
        (r"^(fade|smooth)$", "Fade", "transition", "Other"),
        (r"^(reset|counter.*reset)$", "Reset", "restart", "Other"),
        (r"^(mem|memory|store|save|stored|memo)$", "Memory", "content-save", "Other"),
        (r"^(test|test.*tone)$", "Test", "tools", "Other"),
        (r"^(help)$", "Help", "help-circle-outline", "Other"),
        (r"^(auto)$", "Auto", "auto-fix", "Other"),
        (r"^(program|pgm|prog)$", "Prog", "cog", "Other"),
        (r"^(edit)$", "Edit", "pencil", "Other"),
        (r"^(swap|a/b)$", "Swap", "swap-horizontal", "Other"),
        (r"^(preset)$", "Preset", "view-list", "Other"),
        (r"^(rotate)$", "Rotate", "rotate-right", "Other"),
        (r"^(direct)$", "Direct", "arrow-right-bold-circle", "Other"),
        (r"^(zone)$", "Zone", "home-group", "Other"),
        (r"^(night)$", "Night", "weather-night", "Other"),
        (r"^(rating.*(\+|up))$", "Rating +", "star-plus", "Other"),
        (r"^(rating.*(\-|down))$", "Rating -", "star-minus", "Other"),
        (r"^(library)$", "Lib", "bookshelf", "Other"),
        (r"^(\+|plus)$", "Plus", "plus", "Other"),
        (r"^(\-|minus|dash)$", "Minus", "minus", "Other"),
    ]

    for pattern, name_repl, icon_repl, cat in patterns:
        match = re.search(pattern, n)
        if match:
            final_name = name_repl(match) if callable(name_repl) else name_repl
            final_icon = icon_repl(match) if callable(icon_repl) else icon_repl

            result.update({"name": final_name, "icon": final_icon, "category": cat})
            break

    return result


# --- ABSTRACT PROVIDER ---
class IrRepoProvider(ABC):
    def __init__(self, id: str, name: str, url: str):
        self.id = id
        self.name = name
        self.url = url

    async def download_and_convert(self, broadcast_func=None) -> list[dict]:
        """Downloads, extracts and converts IR data. Returns list of remote dicts with buttons."""
        logger.info("[%s] Starting download and conversion process.", self.name)

        if broadcast_func:
            await broadcast_func(
                {
                    "type": "irdb_progress",
                    "status": "downloading",
                    "db": self.name,
                    "message": f"Starting {self.name}...",
                    "percent": 0,
                }
            )

        logger.info("[%s] Downloading from %s...", self.name, self.url)

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                async with client.stream("GET", self.url) as resp:
                    resp.raise_for_status()

                    total_size = int(resp.headers.get("Content-Length", 0))
                    logger.info(
                        "[%s] Download started, total size: %s bytes",
                        self.name,
                        total_size or "unknown",
                    )
                    downloaded = 0
                    chunks = []
                    last_percent = 0

                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        downloaded += len(chunk)

                        if broadcast_func:
                            if total_size > 0:
                                pct = int((downloaded / total_size) * 50)
                            else:
                                pct = min(40, int(downloaded / (1024 * 200)))

                            if pct > last_percent:
                                last_percent = pct
                                logger.debug("[%s] Download progress: %d%%", self.name, pct)
                                await broadcast_func(
                                    {
                                        "type": "irdb_progress",
                                        "status": "downloading",
                                        "db": self.name,
                                        "message": f"Downloading {self.name}...",
                                        "percent": pct,
                                    }
                                )

                    content = b"".join(chunks)
                    logger.info(
                        "[%s] Download complete, %d bytes received.",
                        self.name,
                        len(content),
                    )

                if broadcast_func:
                    await broadcast_func(
                        {
                            "type": "irdb_progress",
                            "status": "extracting",
                            "db": self.name,
                            "message": f"Extracting {self.name}...",
                            "percent": 50,
                        }
                    )

                logger.info("[%s] Extracting archive...", self.name)
                with tempfile.TemporaryDirectory() as tmp_dir:
                    temp_extract_dir = Path(tmp_dir)
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        z.extractall(temp_extract_dir)
                    logger.info("[%s] Archive extracted.", self.name)

                    if broadcast_func:
                        await broadcast_func(
                            {
                                "type": "irdb_progress",
                                "status": "converting",
                                "db": self.name,
                                "message": f"Processing {self.name}...",
                                "percent": 75,
                            }
                        )

                    logger.info("[%s] Starting conversion process...", self.name)
                    items = list(temp_extract_dir.iterdir())
                    if not items:
                        raise ValueError("Extracted zip is empty")

                    extracted_root = items[0] if len(items) == 1 and items[0].is_dir() else temp_extract_dir

                    remotes = self.convert(extracted_root)
                    logger.info(
                        "[%s] Conversion complete. %d remotes generated.",
                        self.name,
                        len(remotes),
                    )

                if broadcast_func:
                    await broadcast_func(
                        {
                            "type": "irdb_progress",
                            "status": "done",
                            "db": self.name,
                            "message": f"Finished {self.name}",
                            "percent": 100,
                        }
                    )
        except Exception as e:
            logger.error("[%s] Update failed: %s", self.name, e, exc_info=True)
            if broadcast_func:
                await broadcast_func(
                    {
                        "type": "irdb_progress",
                        "status": "error",
                        "db": self.id,
                        "message": f"Error: {e}",
                    }
                )
            raise e

        logger.info("[%s] Provider update process finished successfully.", self.name)
        return remotes

    @abstractmethod
    def convert(self, raw_root: Path) -> list[dict]:
        """Convert raw source files to a list of remote dicts.

        Each dict has the shape:
            {
                "path": str,         # e.g. "flipper/LG/TV"  (no extension)
                "name": str,         # e.g. "TV"
                "provider": str,     # e.g. "flipper"
                "source_file": str,  # e.g. "TV.ir"
                "buttons": [
                    {"name": str, "icon": str, "code": {protocol, address?, command?, ...}}
                ]
            }
        """
