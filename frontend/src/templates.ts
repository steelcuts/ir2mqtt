export interface DeviceTemplate {
    id: string;
    name: string;
    icon: string;
    buttons: { name: string; icon: string }[];
}

export const deviceTemplates: DeviceTemplate[] = [
    {
        id: 'tv',
        name: 'TV',
        icon: 'television',
        buttons: [
            { name: 'Power', icon: 'power' },
            { name: 'Volume Up', icon: 'volume-high' },
            { name: 'Volume Down', icon: 'volume-medium' },
            { name: 'Mute', icon: 'volume-mute' },
            { name: 'Channel Up', icon: 'chevron-up' },
            { name: 'Channel Down', icon: 'chevron-down' },
            { name: 'Source', icon: 'import' },
            { name: 'Menu', icon: 'menu' },
            { name: 'Back', icon: 'arrow-left' },
            { name: 'Up', icon: 'chevron-up' },
            { name: 'Down', icon: 'chevron-down' },
            { name: 'Left', icon: 'chevron-left' },
            { name: 'Right', icon: 'chevron-right' },
            { name: 'OK', icon: 'check' },
            { name: 'Home', icon: 'home' },
            { name: 'Netflix', icon: 'netflix' },
        ]
    },
    {
        id: 'soundbar',
        name: 'Soundbar / Receiver',
        icon: 'speaker',
        buttons: [
            { name: 'Power', icon: 'power' },
            { name: 'Volume Up', icon: 'volume-high' },
            { name: 'Volume Down', icon: 'volume-medium' },
            { name: 'Mute', icon: 'volume-mute' },
            { name: 'Bass Up', icon: 'music-note-plus' },
            { name: 'Bass Down', icon: 'music-note-minus' },
            { name: 'Input Bluetooth', icon: 'bluetooth' },
            { name: 'Input Optical', icon: 'toslink' },
            { name: 'Input HDMI', icon: 'video-input-hdmi' },
        ]
    },
    {
        id: 'ac',
        name: 'Air Conditioner',
        icon: 'air-conditioner',
        buttons: [
            { name: 'Power', icon: 'power' },
            { name: 'Temp Up', icon: 'thermometer-plus' },
            { name: 'Temp Down', icon: 'thermometer-minus' },
            { name: 'Mode Cool', icon: 'snowflake' },
            { name: 'Mode Heat', icon: 'fire' },
            { name: 'Fan Speed', icon: 'fan' },
            { name: 'Swing', icon: 'arrow-oscillating' },
        ]
    },
    {
        id: 'led_strip',
        name: 'LED Strip (RGB)',
        icon: 'led-strip',
        buttons: [
            { name: 'Power On', icon: 'power-on' },
            { name: 'Power Off', icon: 'power-off' },
            { name: 'Brightness Up', icon: 'brightness-5' },
            { name: 'Brightness Down', icon: 'brightness-7' },
            { name: 'Red', icon: 'palette' },
            { name: 'Green', icon: 'palette' },
            { name: 'Blue', icon: 'palette' },
            { name: 'White', icon: 'palette' },
            { name: 'Flash', icon: 'flash' },
            { name: 'Fade', icon: 'transition' },
        ]
    },
    {
        id: 'fan',
        name: 'Fan',
        icon: 'fan',
        buttons: [
            { name: 'Power', icon: 'power' },
            { name: 'Speed', icon: 'speedometer' },
            { name: 'Oscillate', icon: 'arrow-oscillating' },
            { name: 'Timer', icon: 'timer-outline' },
        ]
    },
    {
        id: 'media_player',
        name: 'Media Player',
        icon: 'play-circle',
        buttons: [
            { name: 'Power', icon: 'power' },
            { name: 'Play', icon: 'play' },
            { name: 'Pause', icon: 'pause' },
            { name: 'Stop', icon: 'stop' },
            { name: 'Next', icon: 'skip-next' },
            { name: 'Previous', icon: 'skip-previous' },
            { name: 'Volume Up', icon: 'volume-high' },
            { name: 'Volume Down', icon: 'volume-medium' },
        ]
    }
];